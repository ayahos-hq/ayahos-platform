#!/usr/bin/env bash
set -euo pipefail

# Establish a shared secret for the co-located Ruby RAG sidecar before launching
# either process. Remote RAG without an operator-managed token still fails closed.
source /app/scripts/db/rag_env_bootstrap.sh
ayahos_bootstrap_rag_env

# Verify a pre-migrated schema before Ruby RAG starts. Production application
# startup must never apply DDL; Octopus/operator release step owns migrations.
# Emit one redacted storage-mode and project-ref diagnostic, including local mode.
python /app/scripts/db/runtime_targets.py
source /app/scripts/db/schema_startup.sh
if [[ "${DUAL_LINEAGE_DATABASE_MODE:-local}" == "postgres" ]]; then
  ayahos_prepare_schema
  # One bounded Shared Spine retention pass per start (every deploy and every cold start), before
  # the API serves traffic. Python owns the windows and batch size; its JSON counts go to the log.
  # A failed or slow pass is logged and never stops the API from starting.
  if [[ "${DUAL_LINEAGE_SPINE_RETENTION_ON_START:-false}" == "true" ]]; then
    (
      export DATABASE_URL="${DUAL_LINEAGE_SPINE_DATABASE_URL:-$DATABASE_URL}"
      cd /app
      timeout "${DUAL_LINEAGE_SPINE_RETENTION_TIMEOUT_SECONDS:-60}" python -m dual_lineage.db retention
    ) || echo '{"event":"spine.retention_failed"}' >&2
  fi
fi

cd /app/apps/rag-ruby
BUNDLE_GEMFILE=/app/apps/rag-ruby/Gemfile bundle exec puma -C config/puma.rb &
rag_pid=$!

cd /app/apps/control-ruby
BUNDLE_GEMFILE=/app/apps/control-ruby/Gemfile bundle exec puma -C config/puma.rb &
control_pid=$!

cleanup() {
  kill -TERM "$rag_pid" "$control_pid" "${api_pid:-}" 2>/dev/null || true
  wait "$rag_pid" 2>/dev/null || true
  wait "$control_pid" 2>/dev/null || true
  if [[ -n "${api_pid:-}" ]]; then
    wait "$api_pid" 2>/dev/null || true
  fi
}
trap cleanup SIGTERM SIGINT EXIT

ready=0
for _ in $(seq 1 80); do
  if python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8102/health", timeout=0.5)' >/dev/null 2>&1; then
    ready=1
    break
  fi
  if ! kill -0 "$rag_pid" 2>/dev/null; then
    echo "Ruby RAG sidecar exited before becoming healthy" >&2
    exit 1
  fi
  sleep 0.25
done
if [[ "$ready" != 1 ]]; then
  echo "Ruby RAG sidecar did not become healthy during startup" >&2
  exit 1
fi

cd /app
PYTHONPATH=apps/api/src python -m uvicorn dual_lineage.main:app --host 127.0.0.1 --port "${DUAL_LINEAGE_CORE_PORT:-8101}" &
api_pid=$!
set +e
wait -n "$rag_pid" "$control_pid" "$api_pid"
status=$?
set -e
exit "$status"
