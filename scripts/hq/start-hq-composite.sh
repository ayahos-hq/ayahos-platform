#!/usr/bin/env bash
# Reviewed candidate entrypoint for the exact Core + Workloads context.
# Python remains the public control-plane and action-authority process.
set -euo pipefail

role="\${AYAHOS_RUNTIME_ROLE:-api}"
api_port="\${PORT:-8000}"
rag_port="\${DUAL_LINEAGE_RAG_PORT:-8102}"
control_port="\${DUAL_LINEAGE_CONTROL_PORT:-8103}"
pids=()

fail() {
  echo "HQ COMPOSITE STARTUP BLOCKED: $*" >&2
  exit 2
}

cleanup() {
  local status="\${1:-0}"
  trap - EXIT INT TERM
  for pid in "\${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  for pid in "\${pids[@]}"; do
    wait "$pid" 2>/dev/null || true
  done
  exit "$status"
}

trap 'cleanup 143' INT TERM
trap 'cleanup $?' EXIT

require_value() {
  local name="$1"
  [[ -n "\${!name:-}" ]] || fail "$name must be set"
}

start_rag() {
  require_value DUAL_LINEAGE_RAG_SERVICE_TOKEN
  (
    cd /app/apps/rag-ruby
    exec bundle exec puma -C config/puma.rb
  ) &
  pids+=("$!")
}

start_core() {
  (
    cd /app/apps/api
    exec python -m uvicorn dual_lineage.main:app \
      --host 0.0.0.0 \
      --port "$api_port"
  ) &
  pids+=("$!")
}

start_control() {
  (
    cd /app/apps/control-ruby
    PORT="$control_port" \
      DUAL_LINEAGE_CORE_URL="http://127.0.0.1:$api_port" \
      exec bundle exec puma -C config/puma.rb
  ) &
  pids+=("$!")
}

case "$role" in
  api)
    start_rag
    start_core
    start_control
    ;;
  control)
    start_control
    ;;
  worker)
    cd /app/apps/ruby_worker
    exec bundle exec ruby bin/goblin-workflow work
    ;;
  *)
    fail "unsupported AYAHOS_RUNTIME_ROLE: $role"
    ;;
esac

# Any child exit tears down the composite. A partial stack is not healthy.
wait -n "\${pids[@]}"
status="$?"
cleanup "$status"
