#!/usr/bin/env bash
# Octopus Git-sourced entry point: ignore injected runner digest arguments.
# Intentionally outside the immutable extracted scripts/ci provenance set.
set -euo pipefail

if [[ $# -gt 1 ]] || { [[ $# -eq 1 ]] && [[ ! "$1" =~ ^[0-9a-fA-F]{64}$ ]]; }; then
  printf '%s\n' "Invalid Octopus source digest arguments" >&2
  exit 2
fi

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
exec "${HQ_MANIFEST_PYTHON:-python3}" "$repo_root/scripts/verify-release-manifest.py" \
  --manifest "$repo_root/release-manifest.json"
