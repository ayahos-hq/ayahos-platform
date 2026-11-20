#!/usr/bin/env bash
# Octopus archive checkout has no .git; validate SOURCE-PROVENANCE structurally.
set -euo pipefail

if [[ $# -gt 1 ]] || { [[ $# -eq 1 ]] && [[ ! "$1" =~ ^[0-9a-fA-F]{64}$ ]]; }; then
  printf '%s\n' "Invalid Octopus source digest arguments" >&2
  exit 2
fi

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
manifest="$repo_root/SOURCE-PROVENANCE.json"
release="$repo_root/release-manifest.json"

python3 - "$manifest" "$release" <<'PY'
import json, sys
from pathlib import Path

manifest_path, release_path = Path(sys.argv[1]), Path(sys.argv[2])
m = json.loads(manifest_path.read_text(encoding="utf-8"))
if (m.get("schema_version"), m.get("state"), m.get("target_repository")) != (
    1, "provisional-not-deployed", "ayahos-hq/ayahos-platform"
):
    raise SystemExit("unexpected SOURCE-PROVENANCE schema, state, or target")
expected = m.get("source_files") or {}
if not isinstance(expected, dict) or m.get("source_file_count") != len(expected):
    raise SystemExit("SOURCE-PROVENANCE source_file_count mismatch")
allowed = (".octopus/", "deploy/", "scripts/ci/", "scripts/db/", "scripts/octopus/", "docs/infrastructure/")
for path, record in expected.items():
    if not path.startswith(allowed):
        raise SystemExit(f"disallowed provenance path: {path}")
    if not isinstance(record, dict) or record.get("mode") not in ("100644", "100755"):
        raise SystemExit(f"invalid mode for {path}")
r = json.loads(release_path.read_text(encoding="utf-8"))
if not r:
    raise SystemExit("release-manifest.json missing or empty")
print(f"Attested SOURCE-PROVENANCE ({len(expected)} paths) and release-manifest.json")
PY
