#!/bin/sh
set -eu

base="${SMOKE_BASE_URL:-http://runtime:8000}"
ready=0
i=0
while [ "$i" -lt 40 ]; do
  if curl --connect-timeout 2 --max-time 5 -fsS "$base/health" >/dev/null; then
    ready=1
    break
  fi
  i=$((i + 1))
  sleep 1
done
if [ "$ready" != 1 ]; then
  echo "Container API did not become ready within probe window" >&2
  exit 1
fi
curl -fsS -H 'X-Dual-Lineage-Key: ci-runtime-key' "$base/v1/rag/stats"
curl -fsS -H 'X-Dual-Lineage-Key: ci-runtime-key' \
  -H 'Content-Type: application/json' \
  -d '{"source":"ci/ruby-smoke.md","title":"Ruby smoke","content":"Ruby retrieval is running."}' \
  "$base/v1/rag/documents"
curl -fsS -X POST -H 'X-Dual-Lineage-Key: ci-runtime-key' \
  "$base/v1/rag/search?query=Ruby%20retrieval"
