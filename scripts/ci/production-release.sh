#!/usr/bin/env bash
# Complete local release preflight. No deployment or secret writes.
set -euo pipefail
cd "$(dirname "$0")/../.."

for gate in api web ml rag control worker; do
  echo "== verification gate: $gate =="
  bash scripts/ci/verify.sh "$gate"
done

echo "== release-hardening =="
python scripts/release_gate.py

echo "All local release prerequisites passed."
