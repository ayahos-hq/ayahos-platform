#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."
# shellcheck source=scripts/ci/resource_diagnostics.sh
source scripts/ci/resource_diagnostics.sh

# Octopus exposes project variables through get_octopusvariable; other runners use the environment.
octopus_var() {
  if command -v get_octopusvariable >/dev/null 2>&1; then
    get_octopusvariable "$1" 2>/dev/null || true
  fi
}

TEST_DATABASE_URL="${TEST_DATABASE_URL:-$(octopus_var TEST_DATABASE_URL)}"
CI_TEST_DATABASE_IS_DISPOSABLE="${CI_TEST_DATABASE_IS_DISPOSABLE:-$(octopus_var CI_TEST_DATABASE_IS_DISPOSABLE)}"
export TEST_DATABASE_URL CI_TEST_DATABASE_IS_DISPOSABLE

# Some suites drop the public schema. The guard validates all libpq connection
# parameters, including URL query overrides, before any install or mutation.
source scripts/ci/test_database_guard.sh

# A disposable database is shared by several gates in one run, so each gate that migrates it
# starts from an empty public schema. Never runs unless the database is marked disposable.
reset_disposable_database() {
  if [ "${CI_TEST_DATABASE_IS_DISPOSABLE:-}" = "1" ]; then
    "${1:-python}" - <<'PY'
import os

import psycopg

with psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as connection:
    connection.execute("DROP SCHEMA IF EXISTS public CASCADE")
    connection.execute("CREATE SCHEMA public")
PY
  fi
}

wait_for_pg_isready() {
  local attempt status
  for ((attempt = 1; attempt <= 30; attempt++)); do
    status=0
    pg_isready --dbname "$TEST_DATABASE_URL" --quiet || status=$?
    if [ "$status" -eq 0 ]; then
      return 0
    fi
    if [ "$status" -ge 128 ]; then
      echo "CI PostgreSQL readiness probe terminated by signal (exit $status); not a normal not-ready result" >&2
      ci_resource_snapshot "pg_isready:signal:$status"
      return "$status"
    fi
    sleep 1
  done
  echo "CI PostgreSQL did not become ready after 30 probes" >&2
  ci_resource_snapshot "pg_isready:timeout"
  return 2
}

wait_for_db() {
  python - <<'PY'
import os
import time
import psycopg

url = os.environ["TEST_DATABASE_URL"]
for attempt in range(30):
    try:
        with psycopg.connect(url, connect_timeout=2):
            break
    except psycopg.OperationalError:
        if attempt == 29:
            raise SystemExit("CI PostgreSQL did not become ready")
        time.sleep(2)
PY
}

# Repo-consistency checks: stdlib-only, offline, no database. The service-inventory
# check is a Ruby script (repo language rule: Ruby for ops tooling), so this lane needs ruby. These used to be
# orphaned scripts that nothing ran; they are part of the gate now.
run_consistency_checks() {
  ruby scripts/check_service_inventory.rb
  python scripts/verify_weight_inventory.py
  python -m unittest discover -s scripts/migration -p 'test_*.py'
  python scripts/migration/repositories.py
}

case "${1:-}" in
  api|api-core)
    require_test_database "$1"
    python -m pip install -e './apps/api[dev,control]'
    wait_for_db
    reset_disposable_database
    python -m dual_lineage.db migrate --database-url "$TEST_DATABASE_URL"
    python -m ruff check apps/api apps/sandbox_worker integrations oracle_mcp_server.py
    (cd apps/api && python -m mypy src/dual_lineage)
    python -m pytest -q apps/api/tests --ignore=apps/api/tests/test_minilm_training.py
    # The gVisor suite is a separate image-backed gate; keep the regular worker
    # contract test deterministic and skip-free in environments without runsc.
    python -m pytest -q apps/sandbox_worker/tests --ignore=apps/sandbox_worker/tests/test_e2e_gvisor.py
    run_consistency_checks
    if [ "$1" = api ]; then
      python scripts/release_gate.py
    fi
    ;;
  web)
    # Offline release-target tests protect the primary Cloudflare canary
    # without contacting live endpoints or using any runtime secret.
    python3 -m unittest discover -s scripts/ci/tests -p 'test_*.py'
    corepack enable
    corepack prepare pnpm@9.15.9 --activate
    pnpm install --frozen-lockfile
    pnpm test:web
    pnpm test:site
    pnpm --filter @goblinos-dual-lineage/site lint
    pnpm type-check
    pnpm build:web
    pnpm build:site
    # Chromium is an opt-in verification lane for limited hosted free-tier workers.
    # Site browser fixtures are same-origin and never contact Render or paid providers.
    if [ "${RUN_SITE_BROWSER_E2E:-0}" = 1 ]; then
      pnpm --filter @goblinos-dual-lineage/site exec playwright install chromium-headless-shell
      pnpm --filter @goblinos-dual-lineage/site test:browser
    fi
    node --test deploy/octopus-github-bridge/test/*.test.js
    ;;
  rag)
    require_test_database rag
    export RAG_REQUIRE_PGVECTOR=1
    wait_for_pg_isready
    # One native-gem build at a time on memory-limited Octopus hosted workers.
    (cd apps/rag-ruby && bundle config set path vendor/bundle && bundle install --jobs 1 --retry 2)
    (cd apps/rag-ruby && bundle exec ruby -Itest -e 'Dir["test/**/*_test.rb"].sort.each { |file| require_relative file }')
    ;;
  control)
    (cd apps/control-ruby && bundle config set path vendor/bundle && bundle install --jobs 4 --retry 3)
    (cd apps/control-ruby && bundle exec rake test)
    ;;
  worker)
    require_test_database worker
    wait_for_pg_isready
    if [ ! -x .venv/bin/python ]; then
      # Octopus's worker image ships Python with venv; a stock Ruby image (Drone) may not.
      if ! python3 -m venv .venv 2>/dev/null; then
        rm -rf .venv
        apt-get update -qq
        DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 python3-venv python3-pip
        python3 -m venv .venv
      fi
    fi
    .venv/bin/python -m pip install -e './apps/api[dev,control]'
    export PYTHON_API_CONTRACT_PYTHON="$(pwd)/.venv/bin/python"
    (cd apps/rag-ruby && bundle config set path vendor/bundle && bundle install --jobs 4 --retry 3)
    (cd apps/ruby_worker && bundle config set path vendor/bundle && bundle install --jobs 4 --retry 3)
    python() { .venv/bin/python "$@"; }
    wait_for_db
    reset_disposable_database .venv/bin/python
    .venv/bin/python -m dual_lineage.db migrate --database-url "$TEST_DATABASE_URL"
    (cd apps/ruby_worker && bundle exec ruby -Itest -e 'Dir["test/**/*_test.rb"].sort.each { |file| require_relative file }')
    ruby scripts/test/live_release_smoke_test.rb
    ruby scripts/test/smoke_support_test.rb
    ;;
  ml)
    python -m pip install 'torch>=2.5,<3' --index-url https://download.pytorch.org/whl/cpu
    python -m pip install -r ml-requirements.txt
    python -m pip install -e './apps/api[dev]'
    python -c "import onnxruntime, sentence_transformers, tokenizers, torch, transformers; print('ML dependencies OK')"
    python -m pytest -q apps/api/tests/test_minilm_training.py
    ;;
  consistency)
    run_consistency_checks
    ;;
  *)
    echo "Usage: scripts/ci/verify.sh {api|api-core|web|rag|control|worker|ml|consistency}" >&2
    exit 2
    ;;
esac
