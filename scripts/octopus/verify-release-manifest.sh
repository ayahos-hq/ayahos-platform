#!/usr/bin/env bash
# Octopus Git-sourced entry point: ignore injected runner digest arguments.
# Intentionally outside the immutable extracted scripts/ci provenance set.
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
exec python3 "$repo_root/scripts/verify-release-manifest.py" \
  --manifest "$repo_root/release-manifest.json"
