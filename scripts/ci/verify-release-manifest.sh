#!/usr/bin/env bash
# Octopus entry point: keep runner bootstrap arguments out of Python argparse.
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
exec python3 "$repo_root/scripts/verify-release-manifest.py" \
  --manifest "$repo_root/release-manifest.json"
