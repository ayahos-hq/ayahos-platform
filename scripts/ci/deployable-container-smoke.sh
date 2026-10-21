#!/usr/bin/env bash
set -euo pipefail

# Build and boot the same root image used by the deployable Docker service.
# This step intentionally runs on the Octopus host worker, where Docker is available;
# it must not run inside the worker-tools execution container.
image="goblin-dual-lineage:ci-${OCTOPUS_RELEASE_NUMBER:-local}-${RANDOM:-0}"
name="goblin-dual-lineage-smoke-$$"

cleanup() {
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker image rm "$image" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker build --progress=plain -t "$image" .

docker run -d --name "$name" \
  -p 8000:8000 \
  -e DUAL_LINEAGE_CORE_PORT=8000 \
  -e DUAL_LINEAGE_RUNTIME_API_KEY=ci-runtime-key \
  -e DUAL_LINEAGE_RAG_SERVICE_TOKEN=ci-rag-key \
  -e DUAL_LINEAGE_RAG_URL=http://127.0.0.1:8102 \
  -e DUAL_LINEAGE_DATABASE_MODE=local \
  -e DUAL_LINEAGE_ENV=development \
  "$image" >/dev/null

ready=0
for _ in $(seq 1 40); do
  if curl --connect-timeout 2 --max-time 5 -fsS http://127.0.0.1:8000/health >/dev/null; then
    ready=1
    break
  fi
  sleep 1
done

if [ "$ready" != 1 ]; then
  docker logs "$name" >&2 || true
  echo "Deployable container did not become healthy within probe window" >&2
  exit 1
fi

SMOKE_BASE_URL=http://127.0.0.1:8000 scripts/ci/container-smoke.sh
