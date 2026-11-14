# Google Agent Registry incremental merge ledger

Status: local implementation ledger for open PR #322; no production merge or
deployment claim

Each row is an independent promotion unit. A later row must not be merged by
using evidence from a different source SHA, and a skipped required lane is not
success. The canonical monorepo remains the production authority until the
five-repository extraction gates are independently verified.

PR #322 contains the local implementation for logical units PR 00 through PR
08. The rows below remain the acceptance mapping; they are not separate
production branches or merged commits.

| Unit | Scope | Current local evidence | Promotion blocker |
| --- | --- | --- | --- |
| PR 01 | Google bootstrap | Read-only project/API/global search and IAM observations recorded | Confirm project, residency, billing, and create no publisher identity until explicitly approved |
| PR 02 | Vendor-neutral manifests | Strict Pydantic contracts, digest/provenance checks, malicious-input tests | CI acceptance on exact SHA |
| PR 03 | Read-only adapter | Agent/MCP/skill/endpoint normalization, pagination, retries, cache, signed snapshot fallback | Authenticated adapter proof in staging |
| PR 04 | Reconciliation and publishing | Additive Python publisher, typed Google `Service` writer for approved `NO_SPEC` agents, and bounded Ruby `registry_reconcile` job | Nonproduction publisher identity and write rehearsal |
| PR 05 | Undermind binding | Allowlist, policy-version, envelope, operation, bounded HTTPS read executor, and Action Gateway intent checks; local discovery-to-Spine-to-gateway E2E test | Adversarial CI evidence and gateway integration acceptance |
| PR 06 | Shadow routing | Candidate ranking and independent rollout switches; no execution by default | Shadow benchmark and rollback evidence |
| PR 07 | Admin visibility | Authenticated API status route and read-only operator inventory panel | Deployed authenticated UI/API proof |
| PR 08 | CI and operations | Configuration verifier, deployment-switch verifier, explicit registry checks, runbook, rollback instructions | Exact designated acceptance pipeline with all required lanes |
| PR 09 | Canary and production | Not promoted; switches remain disabled by default | Staged deployment SHA, authenticated live E2E, rollback proof |

## Required evidence per merge

1. Record the branch head SHA before verification and verify that every result
   names that same SHA.
2. Run the focused unit/contract/failure tests, then the complete applicable
   language and integration suites.
3. Inspect the final diff for secrets, permission widening, new provider
   dependencies, and unbounded network or execution paths.
4. Obtain the repository's designated Octopus acceptance result. Retired
   CircleCI and GitHub Actions files are not present and no local configuration
   is proof that an external Octopus run passed.
5. Merge only the verified SHA, record the merge SHA, and verify deployment
   identity separately.

## Rollout switches

The four registry switches are independent and default to disabled:

- discovery: remote read-only lookup;
- publishing: controlled additive registration;
- routing: Overmind shadow/canary proposals;
- execution: final prerequisite before any registry-backed operation.

Rollback is disabling the affected switch and restoring the last approved local
manifest. It must not require Google availability, a live publisher identity,
or a new deployment.

## Current evidence boundary

Latest local evidence in this worktree includes 59 focused registry tests, Ruby
registry reconciliation at 4 runs / 7 assertions with no failures, and 78 web
tests plus TypeScript type-checking. The prior clean-base full API suite reached
1,252 passed and 30 skipped but exposed four unrelated baseline failures in
MiniLM drift determinism and Octopus/resource-diagnostic tests. The read-only Google smoke
proves only the observed account/project/API lookup. None of this proves hosted
CI acceptance, deployment identity, registration writes, live authorization,
or production execution.

## Acceptance matrix

This matrix preserves the distinction between local implementation evidence and
promotion evidence:

| Acceptance condition | Current state | Evidence boundary |
| --- | --- | --- |
| Google project, IAM, location, and cost posture | Partial | Read-only project/API/global search observed; dedicated viewer/publisher identities, billing, and residency approval remain unverified |
| Versioned manifests and adapter | Complete locally | Strict contracts, normalization, caching, retries, signed fallback, and focused tests |
| Registration, search, and reconciliation | Partial | Search and additive reconciliation are locally covered; no remote registration write has been performed |
| Undermind and Action Gateway security | Complete locally | Adversarial contract tests and discovery-to-Spine-to-gateway E2E pass locally |
| Overmind shadow/canary routing | Shadow-only locally | Candidate selection is tested without execution; canary promotion is not enabled |
| Authenticated Admin inventory | Complete locally | Protected API/proxy/UI tests pass; deployed authenticated UI is unverified |
| Offline fallback and rollback | Complete locally | Signed snapshot, outage, switch-off, and bounded executor tests pass; live rollback is unverified |
| Required Octopus lanes and live E2E | Unverified | No exact hosted Octopus result or authenticated live registry flow exists |
| Merge and commit-level delivery evidence | Partial | Open PR #322 is rebased on current `main` at `652f7cb0`; no production merge has been performed |
| Handoff and operating runbook | Complete locally | Architecture, operations, bootstrap, rollout, and evidence-ledger documents are present |
