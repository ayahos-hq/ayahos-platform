#!/usr/bin/env bash
# Verify the primary Cloudflare Pages deployment of this commit, then run the public chat smoke.
# Ported from the former .github/workflows/deploy-public-site.yml (which, despite its name, only
# verified the deployment; the public frontend deploys from Git). Formerly run by the CircleCI `public-site` job on main; now run by hand.
#
# Env: EXPECTED_SHA (required), LIVE_PUBLIC_SITE_URL, FORCE=1 to skip the path filter.
set -euo pipefail

: "${EXPECTED_SHA:?EXPECTED_SHA is required}"
LIVE_PUBLIC_SITE_URL="${LIVE_PUBLIC_SITE_URL:-https://ayahos.pages.dev}"
export LIVE_PUBLIC_SITE_URL

WATCHED_PATHS=(apps/site/ package.json pnpm-lock.yaml pnpm-workspace.yaml scripts/verify_public_site.sh)

if [ "${FORCE:-0}" != 1 ] && git diff --quiet HEAD~1 HEAD -- "${WATCHED_PATHS[@]}"; then
  echo "No public-site paths changed in the last commit; skipping."
  exit 0
fi

pnpm install --frozen-lockfile
test "$(git status --porcelain)" = ""
pnpm --filter @goblinos-dual-lineage/site build

for attempt in $(seq 1 30); do
  build_status="$(curl --silent --show-error --max-time 20 -o build.json -w '%{http_code}' \
    "$LIVE_PUBLIC_SITE_URL/api/build" || true)"
  if [ "$build_status" = "200" ] \
    && jq -e --arg sha "$EXPECTED_SHA" '.build_sha == $sha and .source_branch == "main"' build.json >/dev/null; then
    break
  fi
  if [ "$attempt" -eq 30 ]; then
    echo "public site did not attest $EXPECTED_SHA from main"
    cat build.json || true
    exit 1
  fi
  sleep 10
done
ruby scripts/public_chat_smoke.rb
