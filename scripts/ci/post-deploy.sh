#!/usr/bin/env bash
# Post-deploy live verification for the production Render stack.
#
# This is the automated trigger the post-deploy checks never had: run it after
# Render finishes deploying main (from Octopus via the `live` lane in
# scripts/ci/octopus_verify.sh, or by hand). It is NOT a merge gate - it proves
# claims about the live stack at one exact commit, in AGENTS.md evidence terms.
#
# Required env:
#   EXPECTED_SHA          full commit SHA that was deployed
#   LIVE_RUNTIME_API_KEY  runtime key for the live API (also used by live_e2e)
#   LIVE_SITE_API_KEY     site key for the live release smoke
# Optional env (defaults are the production services):
#   LIVE_API_URL          default https://goblin-dual-lineage-api.onrender.com
#   LIVE_WEB_URL          default https://goblin-dual-lineage-web-live.onrender.com
#   LIVE_PUBLIC_SITE_URL  default https://ayahos.pages.dev
#
# Evidence lands in artifacts/ (live-smoke.json, public-chat-smoke.json,
# live-rate-limit.json, live-rag-smoke.json). Any HOLD or failure exits non-zero.
set -euo pipefail
cd "$(dirname "$0")/../.."

: "${EXPECTED_SHA:?EXPECTED_SHA (full deployed commit SHA) is required}"
: "${LIVE_RUNTIME_API_KEY:?LIVE_RUNTIME_API_KEY is required}"
: "${LIVE_SITE_API_KEY:?LIVE_SITE_API_KEY is required}"

export LIVE_API_URL="${LIVE_API_URL:-https://goblin-dual-lineage-api.onrender.com}"
export LIVE_WEB_URL="${LIVE_WEB_URL:-https://goblin-dual-lineage-web-live.onrender.com}"
export LIVE_PUBLIC_SITE_URL="${LIVE_PUBLIC_SITE_URL:-https://ayahos.pages.dev}"
mkdir -p artifacts

# 1. Authenticated live E2E (waits for web+API to sync to EXPECTED_SHA itself).
RUNTIME_API_KEY="$LIVE_RUNTIME_API_KEY" EXPECTED_SHA="$EXPECTED_SHA" FORCE=1 \
  RUN_TAG="postdeploy-${EXPECTED_SHA:0:7}-$(date +%s)" \
  bash scripts/live_e2e.sh

# 2. Release smoke + evidence publication + rate-limit smoke (deliberately last:
#    it saturates cost/rate-limit buckets). live-release.sh predates Octopus and
#    reads Codefresh variables; map them here so the shim lives in one place.
CF_BRANCH=main CF_REVISION="$EXPECTED_SHA" bash scripts/ci/live-release.sh

echo "Post-deploy verification passed for $EXPECTED_SHA; evidence in artifacts/"
