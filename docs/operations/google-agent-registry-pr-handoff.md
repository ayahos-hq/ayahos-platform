# Google Agent Registry PR handoff

Status: open PR #322; rebased onto current `main`; not merged, deployed, or
live-verified. No Google mutation has been performed.

## Candidate

- Branch: `chore/google-agent-registry-pr00-clean`
- Worktree: `C:\Users\Admin\AyahOS_agent_registry_clean`
- Pull request: #322
- Latest PR head: `652f7cb0234a13ec04280c8355c0c568a04bcb11`
- Canonical production authority: the original Dual-Lineage monorepo
- Provisional extracted repositories: not connected to production

## Local evidence

Run from the repository root with the intended Python environment:

```powershell
python scripts/verify_agent_registry_config.py
python scripts/verify_agent_registry_deployment.py
python -m pytest -q apps/api/tests
python -m pytest -q apps/api/tests -k agent_registry
```

The latest focused results are 59 registry API tests passed, Ruby registry
reconciliation 4 runs / 7 assertions with no failures, 78 web tests passed,
and web TypeScript type-checking passed. The prior clean-base full API suite
reached 1,252 passed and 30 skipped but exposed four unrelated baseline
failures in MiniLM drift determinism and Octopus/resource-diagnostic tests.
Those failures remain a merge blocker; they must not be hidden by skipping or
replacing required lanes. Cloudflare Pages passed for the PR; Vercel was still
pending at the last hosted check.

## Promotion order

1. Review the diff and verify the exact candidate SHA.
2. Resolve or separately clear the current baseline acceptance failures, then
   obtain the designated hosted acceptance result with every required lane
   successful and no unexplained skips.
3. Keep PR #322 open until the designated acceptance and review gates pass.
4. Merge only the verified head SHA after required review.
5. Verify deployment identity separately; do not infer it from a merge result.
6. Keep all four registry switches disabled for the first deployment.
7. Promote discovery, shadow routing, canary, and execution independently,
   recording the manifest digest and rollback result at each stage.

## External prerequisites

- Confirm the Google project, billing, and residency decision.
- Create separate short-lived viewer and narrowly scoped publisher identities
  only after explicit approval.
- Rehearse one nonproduction additive registration; do not register production
  capabilities during PR review.
- Obtain authenticated staging discovery and a live discovery-to-Gateway flow.
- Record the served deployment SHA, rollout switches, Spine observation, and
  rollback behavior.

The current Google evidence is read-only: the selected project has the Agent
Registry API enabled, the global `ayahos` inventory is empty, and no publisher
identity or registration write has been performed.

## Rollback

Disable only the affected registry switch and restore the last approved signed
local snapshot. Existing chat and compute routing must remain available without
Google Registry connectivity. Rollback must not require a new Google write or a
new deployment.
