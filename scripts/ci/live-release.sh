#!/usr/bin/env bash
# Manual release verification only. No deployments or secret writes.
set -euo pipefail
cd "$(dirname "$0")/../.."

: "${LIVE_API_URL:?Set LIVE_API_URL}"
: "${LIVE_PUBLIC_SITE_URL:?Set LIVE_PUBLIC_SITE_URL}"
: "${LIVE_WEB_URL:?Set LIVE_WEB_URL}"
: "${LIVE_RUNTIME_API_KEY:?Configure secret LIVE_RUNTIME_API_KEY}"
: "${LIVE_SITE_API_KEY:?Configure secret LIVE_SITE_API_KEY}"

case "${CF_BRANCH:-}" in main) ;; *) echo "Release check refused: only main is eligible" >&2; exit 1;; esac
expected="$(git rev-parse HEAD)"
if [ -n "${CF_REVISION:-}" ] && [ "$expected" != "$CF_REVISION" ]; then
  echo "Release check refused: cloned revision does not match Codefresh trigger" >&2
  exit 1
fi

export LIVE_EXPECTED_SHA="$expected"
export LIVE_EXPECTED_SITE_SHA="$expected"
export LIVE_SMOKE_OUTPUT="artifacts/live-smoke.json"
export PUBLIC_CHAT_SMOKE_OUTPUT="artifacts/public-chat-smoke.json"
export LIVE_RATE_LIMIT_OUTPUT="artifacts/live-rate-limit.json"
export LIVE_RAG_SMOKE_OUTPUT="artifacts/live-rag-smoke.json"
export BASE_URL="$LIVE_WEB_URL"
mkdir -p artifacts

ruby scripts/public_chat_smoke.rb
ruby scripts/live_release_smoke.rb
ruby scripts/publish_release_evidence.rb

python - <<'PY'
import json
import os
from pathlib import Path

data = json.loads(Path(os.environ["LIVE_SMOKE_OUTPUT"]).read_text())
if data.get("decision") != "RELEASE":
    raise SystemExit("HOLD: live release evidence does not authorize RELEASE")
print("Release evidence decision: RELEASE")
PY

# Deliberately last: saturates cost/rate-limit buckets.
ruby scripts/live_rate_limit_smoke.rb
