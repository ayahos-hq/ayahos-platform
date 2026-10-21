#!/usr/bin/env bash
# Octopus Cloud execution-container checks. Never run DB tests against external DB.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
# shellcheck source=scripts/ci/resource_diagnostics.sh
source scripts/ci/resource_diagnostics.sh
LANE="${1:-}"
CI_STAGE="startup"
# ERR is observed, not handled: no command is placed in an errexit-disabling wrapper.
trap 'ci_log_failure "$?" "$LANE" "$CI_STAGE"' ERR
fail() { ci_resource_snapshot "failure:$LANE"; echo "Octopus CI error: $*" >&2; exit 2; }
octopus_var() {
    if command -v get_octopusvariable >/dev/null 2>&1; then
        get_octopusvariable "$1" 2>/dev/null || true
    fi
}

# Octopus executes Git resources from an archive without a .git directory. Preserve the release
# commit through the environment so release-evidence jobs can still bind their output to the exact
# package under test.
LIVE_EXPECTED_SHA="${LIVE_EXPECTED_SHA:-$(octopus_var Octopus.Release.Git.CommitHash)}"
if [[ "$LIVE_EXPECTED_SHA" =~ ^[0-9a-fA-F]{7,64}$ ]]; then
    export LIVE_EXPECTED_SHA
else
    unset LIVE_EXPECTED_SHA
fi

[ -r /etc/os-release ] || fail "OS identity unavailable"
. /etc/os-release
[ "${ID:-}" = ubuntu ] && [ "${VERSION_ID:-}" = 24.04 ] ||
    fail "expected Ubuntu 24.04 execution container"
[ -f /.dockerenv ] || fail "refusing installs outside isolated container"
[ -d apps/api/src/dual_lineage ] && [ -f pnpm-lock.yaml ] ||
    fail "incomplete Git repository checkout"
case "$LANE" in api|web|ml|rag|worker|control|release|live) ;; *) fail "unsupported lane: $LANE";; esac
ci_resource_snapshot "worker:startup:$LANE"

if [ "$(id -u)" -eq 0 ]; then
    ROOT_CMD=()
else
    command -v sudo >/dev/null || fail "root access required in test container"
    ROOT_CMD=(sudo)
fi
install_packages() {
    if [ "${APT_UPDATED:-0}" -eq 0 ]; then
        "${ROOT_CMD[@]}" apt-get update -qq
        APT_UPDATED=1
    fi
    DEBIAN_FRONTEND=noninteractive "${ROOT_CMD[@]}" apt-get install -y -qq --no-install-recommends "$@"
}
setup_python() {
    install_packages python3.12 python3.12-venv python3.12-dev python3-pip libpq-dev build-essential
    command -v python3.12 >/dev/null || fail "Python 3.12 unavailable"
    if [ ! -x "$ROOT/.venv/bin/python" ]; then
        python3.12 -m venv "$ROOT/.venv"
    fi
    export PATH="$ROOT/.venv/bin:$PATH"
    python -c "import sys; assert sys.version_info >= (3,11)"
}
setup_ruby() {
    install_packages ruby ruby-dev build-essential libpq-dev
    # RubyGems can place executables outside the base image's PATH. Make the
    # active Ruby installation's bin directory visible before checking bundle.
    ruby_gem_bin="$(ruby -e 'print Gem.bindir')"
    case ":$PATH:" in
        *":$ruby_gem_bin:"*) ;;
        *) export PATH="$ruby_gem_bin:$PATH" ;;
    esac
    if ! command -v bundle >/dev/null 2>&1; then
        gem install bundler -v 2.6.9 --no-document
    fi
    command -v bundle >/dev/null 2>&1 || fail "Ruby Bundler unavailable"
}
setup_pgvector() {
    # Ubuntu 24.04 universe provides PostgreSQL 16 with pgvector.
    install_packages postgresql-16 postgresql-client-16 postgresql-16-pgvector
    # Constrain memory for the disposable RAG test database only.
    if [ "$LANE" = rag ]; then
        "${ROOT_CMD[@]}" pg_conftool 16 main set shared_buffers 32MB
        "${ROOT_CMD[@]}" pg_conftool 16 main set work_mem 2MB
        "${ROOT_CMD[@]}" pg_conftool 16 main set maintenance_work_mem 16MB
        "${ROOT_CMD[@]}" pg_conftool 16 main set max_parallel_workers 0
    fi
    ci_resource_snapshot "postgres:before-start:$LANE"
    if ! "${ROOT_CMD[@]}" pg_ctlcluster 16 main start; then
        "${ROOT_CMD[@]}" pg_isready --host 127.0.0.1 --port 5432 --quiet ||
            fail "PostgreSQL 16 could not start"
    fi
    ci_resource_snapshot "postgres:started:$LANE"
    if ! "${ROOT_CMD[@]}" runuser -u postgres -- psql -tAc \
        "SELECT 1 FROM pg_roles WHERE rolname = 'ayahos_ci'" | grep -qx 1; then
        "${ROOT_CMD[@]}" runuser -u postgres -- psql -v ON_ERROR_STOP=1 -c \
            "CREATE ROLE ayahos_ci LOGIN PASSWORD 'octopus_ephemeral_test_only' CREATEDB;"
    fi
    if ! "${ROOT_CMD[@]}" runuser -u postgres -- psql -tAc \
        "SELECT 1 FROM pg_database WHERE datname = 'ayahos_ci'" | grep -qx 1; then
        "${ROOT_CMD[@]}" runuser -u postgres -- createdb -O ayahos_ci ayahos_ci
    fi
    "${ROOT_CMD[@]}" runuser -u postgres -- psql -v ON_ERROR_STOP=1 -d ayahos_ci -c \
        "CREATE EXTENSION IF NOT EXISTS vector;"
    export TEST_DATABASE_URL="postgresql://ayahos_ci:octopus_ephemeral_test_only@127.0.0.1:5432/ayahos_ci"
    export DATABASE_URL="$TEST_DATABASE_URL"
    case "$TEST_DATABASE_URL" in
        postgresql://ayahos_ci:*@127.0.0.1:5432/ayahos_ci) ;;
        *) fail "unexpected disposable PostgreSQL URL" ;;
    esac
}

case "$LANE" in
    api)
        setup_python
        setup_ruby
        setup_pgvector
        bash scripts/ci/verify.sh api-core
        ;;
    web)
        command -v node >/dev/null || fail "Node.js unavailable"
        command -v npm >/dev/null || fail "npm unavailable"
        node -e 'const [m,n]=process.versions.node.split(".").map(Number);if(m<20||(m===20&&n<9)) process.exit(2)'
        if ! command -v corepack >/dev/null; then
            npm install -g corepack@0.34.5
        fi
        bash scripts/ci/verify.sh web
        ;;
    ml)
        setup_python
        bash scripts/ci/verify.sh ml
        ;;
    rag)
        CI_STAGE="ruby-bootstrap"
        ci_resource_snapshot "rag:before-ruby-bootstrap"
        setup_ruby
        ci_resource_snapshot "rag:after-ruby-bootstrap"
        CI_STAGE="postgres-bootstrap"
        ci_resource_snapshot "rag:before-postgres-bootstrap"
        setup_pgvector
        ci_resource_snapshot "rag:after-postgres-bootstrap"
        export RAG_REQUIRE_PGVECTOR=1
        CI_STAGE="pgvector-tests"
        ci_resource_snapshot "rag:before-pgvector-tests"
        bash scripts/ci/verify.sh rag
        ci_resource_snapshot "rag:after-pgvector-tests"
        ;;
    worker)
        setup_python
        setup_ruby
        setup_pgvector
        export RUN_PYTHON_API_CONTRACT=1
        export RUBY_WORKER_REQUIRE_INTEGRATION=1
        bash scripts/ci/verify.sh worker
        ;;
    control)
        setup_ruby
        bash scripts/ci/verify.sh control
        ;;
    live)
        # Post-deploy only: verifies the live stack at EXPECTED_SHA. This is not
        # a merge gate and needs live smoke secrets as Octopus variables:
        # LIVE_RUNTIME_API_KEY, LIVE_SITE_API_KEY, EXPECTED_SHA (the deployed
        # main commit). LIVE_API_URL / LIVE_WEB_URL / LIVE_PUBLIC_SITE_URL may
        # override the live defaults in scripts/ci/post-deploy.sh.
        setup_python
        setup_ruby
        command -v jq >/dev/null || install_packages jq
        export LIVE_RUNTIME_API_KEY="${LIVE_RUNTIME_API_KEY:-$(octopus_var LIVE_RUNTIME_API_KEY)}"
        export LIVE_SITE_API_KEY="${LIVE_SITE_API_KEY:-$(octopus_var LIVE_SITE_API_KEY)}"
        export EXPECTED_SHA="${EXPECTED_SHA:-${LIVE_EXPECTED_SHA:-}}"
        bash scripts/ci/post-deploy.sh
        ;;
    release)
        setup_python
        setup_ruby
        setup_pgvector
        python -m pip install -e './apps/api[dev,control]'
        python -m dual_lineage.db migrate --database-url "$TEST_DATABASE_URL"
        python scripts/release_gate.py
        ;;
esac

printf 'Required Octopus lane %s completed for source revision package\n' "$LANE"
