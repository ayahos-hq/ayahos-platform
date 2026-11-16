#!/usr/bin/env bash
# Build and boot the exact HQ candidate on a worker with local Docker.
set -euo pipefail
umask 077

fail() { printf 'HQ composite verification failed: %s\n' "$*" >&2; exit 1; }

if (( $# > 1 )) || { (( $# == 1 )) && [[ ! "$1" =~ ^[0-9a-fA-F]{64}$ ]]; }; then
    fail "unexpected Octopus Git source arguments"
fi

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
platform_sha="${HQ_PLATFORM_SHA:-}"
base_image="${HQ_PYTHON_BASE_IMAGE:-}"
if command -v get_octopusvariable >/dev/null; then
    [[ "$(get_octopusvariable Octopus.Project.Name)" == "AyahOS HQ Verification" ]] ||
        fail "unexpected Octopus project"
    [[ "$(get_octopusvariable Octopus.Environment.Name)" == "Development" ]] ||
        fail "unexpected Octopus environment"
    platform_sha="$(get_octopusvariable HQ.PlatformSha)"
    base_image="$(get_octopusvariable HQ.PythonBaseImage)"
fi
[[ "$platform_sha" =~ ^[0-9a-f]{40}$ ]] || fail "a full candidate Platform SHA is required"
[[ "$base_image" =~ ^[a-z0-9][a-z0-9./:_-]*@sha256:[0-9a-f]{64}$ ]] ||
    fail "a digest-pinned Python base image is required"

scratch="$(mktemp -d)"
container=""
tag="ayahos-hq-composite-verification:${scratch##*/}"
cleanup() {
    if [[ -n "$container" ]]; then docker rm -f "$container" >/dev/null 2>&1 || true; fi
    docker image rm "$tag" >/dev/null 2>&1 || true
    rm -rf -- "$scratch"
}
trap cleanup EXIT

manifest="$root/release-manifest.json"
workspace="${HQ_VERIFIED_WORKSPACE:-"$scratch/workspace"}"
if command -v get_octopusvariable >/dev/null || [[ -z "${HQ_VERIFIED_WORKSPACE:-}" ]]; then
    workspace="$scratch/workspace"
    python3 "$root/scripts/assemble-hq-workspace.py" --manifest "$manifest" \
        --platform-head "$platform_sha" --workspace "$workspace"
fi
[[ "$(git -C "$workspace/ayahos-platform" rev-parse HEAD)" == "$platform_sha" ]] ||
    fail "workspace Platform SHA differs from the selected commit"
python3 "$root/scripts/verify-release-manifest.py" --manifest "$manifest" --workspace-root "$workspace"

platform="$workspace/ayahos-platform"
context="$scratch/context"
python3 "$platform/scripts/hq/compose-hq-runtime.py" --manifest "$manifest" \
    --workspace "$workspace" --output "$context"

inputs="$(python3 - "$context/COMPOSITE-SOURCE-MANIFEST.json" <<'PY'
import json
import sys
from pathlib import Path

provenance = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
refs = provenance["checkout_shas"]
print(refs["ayahos-core"], refs["ayahos-workloads"], provenance["release_manifest_sha256"])
PY
)"
read -r core_sha workloads_sha manifest_sha <<< "$inputs"
docker build --tag "$tag" --build-arg "PYTHON_BASE_IMAGE=$base_image" \
    --build-arg "CORE_SHA=$core_sha" --build-arg "WORKLOADS_SHA=$workloads_sha" \
    --build-arg "PLATFORM_SHA=$platform_sha" --build-arg "RELEASE_MANIFEST_SHA256=$manifest_sha" "$context"

# Keep the smoke container on loopback only and use synthetic credentials.
container="$(docker run --detach --network none \
    -e DUAL_LINEAGE_RUNTIME_API_KEY=ci-runtime-key \
    -e DUAL_LINEAGE_RAG_SERVICE_TOKEN=ci-rag-key \
    -e DUAL_LINEAGE_RAG_URL=http://127.0.0.1:8102 \
    -e DUAL_LINEAGE_DATABASE_MODE=local -e DUAL_LINEAGE_ENV=local "$tag")"

if ! docker exec -i "$container" python - <<'PY'
import json
import time
from urllib.request import build_opener, ProxyHandler

services = {
    8000: "goblinos-dual-lineage-api",
    8102: "goblinos-rag-ruby",
    8103: "ayahos-control-ruby",
}
client = build_opener(ProxyHandler({}))
deadline = time.monotonic() + 45
while time.monotonic() < deadline:
    missing = []
    for port, expected in services.items():
        try:
            with client.open(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                body = json.load(response)
            if body.get("status") == "ok" and body.get("service") == expected:
                continue
        except (OSError, ValueError):
            pass
        missing.append(expected)
    if not missing:
        print("Healthy: " + ", ".join(services.values()))
        break
    time.sleep(1)
else:
    raise SystemExit("Missing healthy services: " + ", ".join(missing))
PY
then
    docker logs "$container" >&2 || true
    fail "the isolated composite did not become healthy"
fi
printf 'Verified local composite image for Platform %s\n' "$platform_sha"
