#!/usr/bin/env bash
# Dedicated AyahOS HQ Verification Octopus project entrypoint. No status posting.
set -euo pipefail
umask 077
fail() { echo "HQ OCTOPUS ARTIFACT GATE BLOCKED: $*" >&2; exit 2; }
repo_root="$(cd -- "$(dirname -- "$BASH_SOURCE")/../.." && pwd)"
cd "$repo_root"
if (( $# > 1 )) || { (( $# == 1 )) && [[ ! "$1" =~ ^[0-9a-fA-F]{64}$ ]]; }; then
  fail "unexpected Octopus Git source arguments"
fi
command -v get_octopusvariable >/dev/null || fail "must execute in Octopus"
project="$(get_octopusvariable Octopus.Project.Name)"
[[ "$project" == "AyahOS HQ Verification" ]] || fail "wrong Octopus project"
release_sha="$(get_octopusvariable Octopus.Release.Git.CommitHash)"
[[ "$release_sha" =~ ^[0-9a-f]{40}$ ]] || fail "missing exact release platform SHA"
[[ "$HQ_PLATFORM_SHA" == "$release_sha" ]] || fail "platform commit mismatch"
command -v git >/dev/null || fail "git is required"
python3 scripts/verify-release-manifest.py --manifest release-manifest.json
python3 scripts/run-hq-offline-tests.py
workroot="$(mktemp -d)"
trap 'rm -rf -- "$workroot"' EXIT
python3 scripts/assemble-hq-workspace.py \
  --manifest release-manifest.json \
  --platform-head "$release_sha" \
  --workspace "$workroot/workspace"
if [[ -n "$HQ_OCI_LOCK" ]]; then
  python3 scripts/build-hq-artifacts.py --manifest release-manifest.json \
    --workspace "$workroot/workspace" --output "$workroot/artifacts" \
    --oci-lock "$HQ_OCI_LOCK"
else
  python3 scripts/build-hq-artifacts.py --manifest release-manifest.json \
    --workspace "$workroot/workspace" --output "$workroot/artifacts"
fi
python3 scripts/build-hq-artifacts.py --verify-only --output "$workroot/artifacts"
# The Octopus run must separately attest all integration, restore, live and rollback
# steps before reporting an authoritative release result or GitHub required status.
echo "Source artifacts verified for $release_sha; no production authorization"
