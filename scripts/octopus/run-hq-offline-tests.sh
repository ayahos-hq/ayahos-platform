#!/usr/bin/env bash
# Octopus Git-sourced entry point: ignore injected runner digest arguments.
set -euo pipefail

if [[ $# -gt 1 ]] || { [[ $# -eq 1 ]] && [[ ! "$1" =~ ^[0-9a-fA-F]{64}$ ]]; }; then
  printf '%s\n' "Invalid Octopus source digest arguments" >&2
  exit 2
fi

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
exec python3 "$repo_root/scripts/run-hq-offline-tests.py"
