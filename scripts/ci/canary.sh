#!/usr/bin/env bash
# Scheduled public canary: no secrets, no inference spend beyond one public
# chat round-trip. Safe to run on a timer (cron, Octopus scheduled trigger).
# Exits non-zero when the public site is down, on the wrong commit (when
# EXPECTED_SHA is given), or the public chat path fails.
#
# Env: LIVE_PUBLIC_SITE_URL (default https://ayahos.pages.dev),
#      EXPECTED_SHA (optional; when set, /api/build must attest it from main)
set -euo pipefail
cd "$(dirname "$0")/../.."

LIVE_PUBLIC_SITE_URL="${LIVE_PUBLIC_SITE_URL:-https://ayahos.pages.dev}"
export LIVE_PUBLIC_SITE_URL
mkdir -p artifacts

status="$(curl --silent --show-error --max-time 30 -o artifacts/canary-build.json -w '%{http_code}' \
  "$LIVE_PUBLIC_SITE_URL/api/build" || true)"
if [ "$status" != "200" ]; then
  echo "CANARY FAIL: $LIVE_PUBLIC_SITE_URL/api/build returned $status" >&2
  exit 1
fi
# Even without EXPECTED_SHA, a canary must attest a real main-branch
# 40-character release SHA. Otherwise an unrelated 200 could pass silently.
python3 - "${EXPECTED_SHA:-}" <<'PY'
import json, re, sys
from pathlib import Path
data = json.loads(Path("artifacts/canary-build.json").read_text())
actual = data.get("build_sha")
assert isinstance(actual, str) and re.fullmatch(r"[a-fA-F0-9]{40}", actual), "invalid or missing build_sha"
assert data.get("source_branch") == "main", f"source_branch {data.get('source_branch')} != main"
expected = sys.argv[1]
if expected:
    assert re.fullmatch(r"[a-fA-F0-9]{40}", expected), "EXPECTED_SHA must be a full SHA"
    assert actual.lower() == expected.lower(), f"build_sha {actual} != {expected}"
print("canary: /api/build attests main at", actual)
PY
ruby scripts/public_chat_smoke.rb
echo "Canary passed: $LIVE_PUBLIC_SITE_URL"
