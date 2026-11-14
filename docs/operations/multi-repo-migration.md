# AyahOS E2E multi-repository migration runbook

## Documentation checkpoint — 2026-10-25 — superseding status overlay

The 2026-10-22 re-pin milestones below are historical source-integrity checkpoints, **not** the latest `main` SHAs. On 2026-10-25 the observed default-branch heads were site `a1f94618`, core `be672280`, admin `223a3b6c`, platform `094328e6`, and workloads `e4de3aab`; independently re-check all full SHAs before assembling a release.

**Progress since the historical checkpoint:** [Platform PR #34](https://github.com/ayahos-hq/ayahos-platform/pull/34) merged a Linux-native exact-five-repo source assembler. The PR reports a successful independent **Octopus HQ Verification Development** release 0.0.18 / Deployments-351 with three required source checks. This *does* establish limited Development source verification, so blanket claims that there is no HQ Octopus project or no HQ Octopus run are stale. It **does not** establish a cross-repo built/attested container, genuine PostgreSQL 16/pgvector integration or restore, production status context, Cloudflare Pages Git repoint, authenticated admin/chat, real gVisor, DNS changes or rollback. [Platform PR #36](https://github.com/ayahos-hq/ayahos-platform/pull/36) remains unmerged artifact/OCI work. Production source ownership is unchanged until explicit cutover gates pass. Do not repoint the incumbent Octopus bridge.


**Status as of 2026-10-22:** Phase 0 inventory is complete (`docs/operations/migration-phase0-inventory.md`, PR #293) and Phase 1 creation is verified via owner GitHub API (org-settings hardening remains). All five destination repos have been re-pinned to monorepo `a7ef41f` with byte-identical source and isolated CI evidence (see the a7ef41f checkpoint below for destination SHAs and evidence; the site repo carries one documented known-flake exception). **No cutover of any kind has been performed:** Octopus connection, previews, production traffic, DNS, secrets and original monorepo transfer remain **pending/not started**. Production stays on the original monorepo.

## Phase 2–6 source-sync checkpoint — a7ef41f re-pin (2026-10-22)

All destination snapshots were re-pinned from `df20951` to monorepo `a7ef41fe1ec6a680bc734a5d54890fb13972d3a3` in one run. Post-merge verification compared blob SHA and file mode for every provenance-manifest file against the monorepo at that commit: **714 files checked across the five repos, 0 mismatches**. The monorepo was read-only throughout this sync.

- **Site** — `ayahos-hq/ayahos-site` PR #8 merged at `a90df712d749e81ef4cbaf8c4d1e1f9155c5e93d`: 93 site + 9 vendored `packages/shared` files byte-identical (3 added, 7 updated, 0 deleted in the provenance manifest; 105 files checked including `.gitignore`, LICENSE and NOTICE). Isolated CI passed provenance, frozen install, lint, type-check, unit tests and static export; the browser suite went 29/30 with the sole failure the known pre-existing `resilience.pw.ts:35` flake — the test file and the code it exercises are byte-identical at both source pins, and PR #7 was merged past the same failure. PR #8 was merged on that precedent after the evidence was recorded on the PR; post-merge provenance verification passed. Cutover still requires the owner Cloudflare preview + Pages Git repoint (gates 5–6).
- **Core** — `ayahos-hq/ayahos-core` PR #8 merged at `5b3a7e6ad2a553ceeaa3b10efc23e2a43c8c0ee8`: provenance scope expanded 308 → 355 files (49 added, 2 deleted, 47 modified), all byte-identical; Dockerfile, Makefile and `.dockerignore` are also byte-identical. Isolated CI green: source verification, policy smoke, and PostgreSQL 16 + pgvector migration smoke. No deployment from the new repo.
- **Admin** — `ayahos-hq/ayahos-admin` PR #3 merged at `b67833f1f0b1994f96a4efcf707054b06f9e7e57`: 81 web + 9 shared files byte-identical (14 added, 16 updated, 1 deleted — `brand-theme.css`, folded into the single stylesheet upstream). Isolated CI green on the PR and on post-merge main (provenance, frozen install, TypeScript, 88 tests, server build). Operator-auth verification against a controlled backend is still outstanding.
- **Platform** — `ayahos-hq/ayahos-platform` PR #4 merged at `5eaeb8a8525a1cf728b7cb3cd039acd6930cedfd`: curated set expanded 50 → 61 files (11 added — including `deploy/cloudrun/*`, `deploy/datadog/*` and `deploy/node-001/*` — 14 updated, 0 deleted), all byte-identical with modes; source verification green. Cross-repo Octopus release and the RAG exit-137 diagnosis remain blocked on Octopus server evidence (external). This repository's visibility is **public by owner decision** (confirmed 2026-10-22); the sync made no visibility change.
- **Workloads** — `ayahos-hq/ayahos-workloads` PR #6 merged at `3f69d6eaee02e88d571c818b78d400ad595c57bc`: Ruby worker section expanded 46 → 48 files (2 added, 15 updated, 0 deleted across the manifest); 103 manifest files verified byte-identical (105 including LICENSE and NOTICE). All four isolation workflows green (verify/RAG, control, sandbox, worker) and the post-merge main run passed. Service contracts, PG integration and a real gVisor run remain outstanding.
- **Contracts (Phase 7 decision):** unchanged — `ayahos-contracts` is **not warranted now**. The monorepo is **not** archived; it remains canonical and production stays on it until the cutover gates pass.

## Phase 2–6 source-sync checkpoint (2026-10-22)

All destination snapshots were re-pinned to monorepo `df20951d3ba7e8e58effb4c06b699322739e28a5` in one run (issue #243 comments carry the per-phase evidence):

- **Site** — `ayahos-hq/ayahos-site` PR #7 merged at `c896e0e3e9158b7923d5959c733cb19f48075404`: 90 site + 9 vendored `packages/shared` files byte-identical (the monorepo site depends on the shared package since PR #292; vendoring preserves the provenance model). Isolated CI green except Playwright 26/27 — sole failure the known `resilience.pw.ts:35` flake, also intermittent on monorepo main. Cutover still requires the owner Cloudflare preview + Pages Git repoint (gates 5–6).
- **Core** — `ayahos-hq/ayahos-core` PR #7 merged at `5aa6a844ecebc7c13263c8dd4a87ef0bbf26dcf3`: 308/308 files byte-identical; isolated CI green **including PostgreSQL 16 + pgvector migration smoke**. No deployment from the new repo.
- **Admin** — `ayahos-hq/ayahos-admin` PR #2 merged at `068d5a6510155b02b995cc91a9a977aad7afc1b3`: 68 web + 9 shared files byte-identical; isolated CI green (install, type-check, 73 tests, server build). Operator-auth verification against a controlled backend is still outstanding.
- **Platform** — `ayahos-hq/ayahos-platform` PR #2 merged at `08266b92c84e217c959e910c8152ebbdaec1c0be`: 50/50 curated files byte-identical with modes; source verification green. Cross-repo Octopus release and the RAG exit-137 diagnosis remain blocked on Octopus server evidence (external).
- **Workloads** — `ayahos-hq/ayahos-workloads` PR #5 merged at `60323d28283eddeaed05421370f0055e1832b23c`: source import complete (RAG 12 + control 14 + sandbox 11 + Ruby worker 46 + ML/research 18), all four isolation workflows green (worker: 115 DB-free runs, 0 failures; PG-backed tests explicitly gated). Service contracts, PG integration and a real gVisor run remain outstanding.
- **Contracts (Phase 7 decision):** `ayahos-contracts` is **not warranted now** — the shared package has two consumers pinned to the same source SHA, and the Ruby client is generated. Revisit at the first independent deployment or a third consumer. The monorepo is **not** archived; it remains canonical.

## Confirmed account access and extraction checkpoint (2026-10-21)

- Organization `ayahos-hq` exists on GitHub Free. The connected ChatGPT GitHub App has an organization-scoped installation and **admin/read/write** visibility for all five **private** repositories: `ayahos-site`, `ayahos-core`, `ayahos-admin`, `ayahos-platform`, `ayahos-workloads`. The prior access-blocker section below is historical and is now **resolved**; do not re-run the create-repositories script.
- `ayahos-site` [PR #1](https://github.com/ayahos-hq/ayahos-site/pull/1) was merged as `3bfc78bf7c915c1d8a12a3fee5b1ecdbf1624520`. It copies 72/72 tracked `apps/site` source blobs from monorepo commit `ab2d7d916cce26c825040ca0f66e5f81821b12e1` **byte-identically**, preserving binary favicon, Functions, tests and original paths. The exported root includes a site-only pnpm workspace, root lockfile, LICENSE and NOTICE, and a Git-blob-SHA provenance manifest. Its root README explicitly forbids live deployment pending verification.
- Site-only, secret-free, low-resource CI: [site PR #2](https://github.com/ayahos-hq/ayahos-site/pull/2) adds a bounded 12-minute GitHub Actions verification workflow, initially pending tests; **it does not supersede Octopus for production release**. The known extra `apps/web` pnpm lockfile importer still needs independent frozen-install validation. Do not confuse GitHub Actions allowance with a verified zero-overage billing budget; GitHub organization billing guard must be reviewed separately.
- `ayahos-core`, `ayahos-admin`, `ayahos-platform`, `ayahos-workloads` each have an initial private non-deployment README and no copied application/runtime source, no hosting integrations, and no credentials.
- **Release gate:** No Cloudflare Git cutover, DNS changes, Render or Google Cloud modifications, secrets transfer, paid external CI, or original monorepo archiving until standalone checks, test evidence, rollback and approved account actions complete.

## Verified isolation checkpoint (2026-10-21, after source extraction)

The organization and five private repositories are connected to the organization-scoped GitHub App. The original monorepo remains the production source.

- **Public site:** [`ayahos-site` PR #6](https://github.com/ayahos-hq/ayahos-site/pull/6) merged the newer SSE terminal-frame fixes from the monorepo. The isolated Actions run [39603820743](https://github.com/ayahos-hq/ayahos-site/actions/runs/39603820743) passed frozen pnpm install, source provenance, lint, TypeScript, Next.js static build, **156 Vitest cases and 20 local-mock Playwright browser tests**. This does not establish actual Cloudflare preview/authenticated runtime equivalence.
- **Governed core:** [`ayahos-core` PR #1](https://github.com/ayahos-hq/ayahos-core/pull/1) merged the exact source snapshot. Git tree comparison matched **291/291** API and architecture files. [Core PR #4](https://github.com/ayahos-hq/ayahos-core/pull/4) merged a low-resource isolated Python 3.11 smoke check: [Actions run 39607177737](https://github.com/ayahos-hq/ayahos-core/actions/runs/39607177737) installed the Python API and passed **39** deterministic Undermind, Action Gateway, actuator-boundary and in-memory Shared Spine tests. Independent source/syntax checks also passed. Full PostgreSQL 16/pgvector, Ruby worker contracts, live authentication/streaming, provider routing and Octopus release gates are **not yet verified**.
- A redundant concurrent core extraction PR was closed after verifying its **297 Git tree blobs were identical** to the already-merged source. A redundant alternative core CI PR was also closed rather than running duplicate free-tier Actions jobs.
- **Security:** Credential-shaped strings detected in core source tests were identified as intentional secret-detection fixtures, not runtime credentials; a comprehensive secret audit is still pending. Never push actual secrets, secrets in previews or CI logs.
- **Admin/platform/workloads:** Other destination repositories are initialized but not yet independently buildable or deployed. Do not treat an extraction branch as an approved runtime.
- **Production invariant:** No Cloudflare, Vercel fallback, Render, Google Cloud, DNS, encrypted credentials or original monorepo cutover has been performed in this phase.

## Verified operator UI isolation (2026-10-21)

[`ayahos-admin` PR #1](https://github.com/ayahos-hq/ayahos-admin/pull/1) merged at `6b9ac3d3be0ba60c66a0f5f7c5635438aee0a18c`. The private `apps/web` operator UI is staged from source SHA `98941434109a34af7b15791981fc47af86a307d9` with **41/41 original Git blob hashes** matched. Its root pnpm workspace contains only `apps/web`; the inactive public-site lockfile importer was removed without changing the operator dependency pins.

GitHub Actions run [39608597752](https://github.com/ayahos-hq/ayahos-admin/actions/runs/39608597752) passed frozen pnpm install, TypeScript, **24/24 Vitest cases** and Next.js server build. This verifies an isolated build, **not** authenticated operator readiness, cross-repo API compatibility, safe production secrets or deployment.

The existing Render operator service, customer Cloudflare Pages site, Vercel backup, governance API, provider routing, DNS and secrets remain unchanged. Do not deploy the admin repository before authorization, audit redaction, staging, Octopus release and rollback are verified.

## Phase 0 — inventory and freeze dangerous changes

- Capture current production and Git SHAs, sites, endpoints, external Git integrations, DNS, database schema, webhooks, container build context, dependencies, secrets **names only**, quota/billing settings and recovery artifacts.
- Confirm live chat, auth, SSE, 429, abort, trace, provider failure, DB and operator status. Do not use a single OK response to certify everything.
- Diagnose Octopus hosted-worker exit 137 using cgroup OOM counters, parent-worker metrics, task limits and timestamps. Keep real PostgreSQL 16+pgvector test mandatory; no silent SQLite swap or skipped test.
- Baseline a non-destructive rollback and a redacted release evidence template. Keep active CI/deploy paths unchanged.

**Exit:** complete dependency matrix and host identities; no unknown user-facing critical path.

## Phase 1 — GitHub organization

Account owner uses https://github.com/organizations/new for a **GitHub Free** organization, display `AyahOS`, with available approved handle (proposed `ayahos-hq`). Create five **empty private repos** in one namespace. The connected GitHub app used for this plan cannot create organizations or repositories or transfer ownership, so this phase requires owner action or an authorized tool with those exact capabilities.

- Keep `fuaadabdullah/AyahOS_Dual_Lineage` as original source; do not transfer it first.
- Assign minimal roles; enable account/org 2FA/passkeys, CODEOWNERS/branch checks where available on Free, least-privilege GitHub and Octopus tokens.
- Limit Actions permissions, use read-only tokens by default and explicit narrow write scopes. Do not grant a broad reusable workflow read policy to untrusted collaborators.
- Record verified org handle/repo URLs, private visibility and settings; only then replace manifest placeholders.
- Optionally configure organization profile `.github` repository and an organization project board; these are organizational aids, not production dependencies.

**Exit:** all repos exist privately under one verified organization, with scoped access and no public site deployment.

## Account setup follow-up (2026-10-21)

The owner reported the GitHub Free organization `ayahos-hq` and **five empty private repos** created under that namespace with `fuaadabdullah` as organization administrator. **This is user-confirmed, not independently verified by the connected GitHub App.**

The currently connected ChatGPT GitHub App installation is on personal account `fuaadabdullah` only. `get_repo` returned 404 for all five `ayahos-hq/*` private repos, and no organization installation appeared in `list_installations`. Private repository 404 can mean **not authorized**, not necessarily missing. The repository creation script must **not** be rerun blindly as a substitute for connector access.

**Owner-only access grant:**

1. Open [GitHub organization installed apps](https://github.com/organizations/ayahos-hq/settings/installations); identify the GitHub App used by this ChatGPT GitHub connection. If it isn't present, install **the same app** onto the `ayahos-hq` organization; a personal-account installation does not automatically include org-owned private repos.
2. Select **Only select repositories**, choosing all five AyahOS repositories; review and approve the app permissions. Keep them private. No token or secret should be posted to chat or committed.
3. Confirm ChatGPT's GitHub connector can enumerate the `ayahos-hq` installation and read each `get_repo` with `visibility=private` and required push permissions. If the connector needs reconnection, do so in ChatGPT's plugin connection settings.
4. Record each destination repository ID and initial default branch (or empty status). Some newly created *empty* repos have no usable `main` commit; initialize only through an authenticated approved operation, then verify `main` before exporting or opening PRs.

**Do not** grant public visibility, repoint Cloudflare's production Git integration, transfer original source, disable CI checks or copy live credentials merely to resolve 404. Keep all downstream extraction stages blocked until read/write access is verified.

## Phase 2 — extract site first

- Stage `apps/site` and current root pnpm files. Repair standalone workspace scripts, lockfile, source links, static `out/`, Cloudflare Functions, Next.js 16 builds, and no preview prod secrets.
- Run type/lint/unit/Playwright plus exact build identity test. Use separate preview; keep current Cloudflare production bound to original repository.
- Exercise valid/invalid/missing key; real SSE fragments and terminal event; abort, retry, backpressure, rate limiting 429, provider 503, CORS, XSS-safe Markdown and short/mobile screens.
- Establish new Git integration and release provenance with exact SHA; switch only after preview E2E passes. Keep Vercel pinned as rollback and validate `/backup`. Recheck custom-domain requests and function env bindings.
- On regression, roll back Cloudflare artifact or routing; no DB schema destruction.

**Exit:** separate site deploy + verified authenticated live-safe smoke + usable rollback.

## Phase 3 — extract core authority

- Trace every import and Dockerfile path. `apps/api` currently relies on other application/worker context; resolve this before building alone, not by adding a default-deny bypass.
- Keep Python deterministic Undermind, Shared Spine, Overmind orchestration and Action Gateway authority co-owned. Ruby gateway never duplicates authorization; ML stays shadow/advisory where currently constrained.
- Use schema versioning and backwards compatible HTTP/events with typed identity, idempotency, budget, cancellation, intent and approval evidence. Test both site versions against both compatible core versions.
- Existing Render stays active. Deploy Cloud Run staging only after verified $0 quotas, memory, cold start, max instances, scaling, egress, DB access, secured provider creds and billing limits. Verify Node 001 offline/provider failure.
- Record DB expand/contract version and restoration path; canary and switch only after Octopus integration gates and authenticated live probes. Revert to last verified artifact when failed.

**Exit:** core independently buildable, deterministic action tests pass, full trace preserved, reversible live migration.

## Phase 4 — extract admin

- Stage `apps/web`, repair workspace imports, pin dependencies; verify private operator authn/authz, mutation approval, CSRF, trace redaction, audit logging, no admin secrets in bundles or previews.
- Retain existing operator route until isolated staging and privilege-negative tests pass. UI is not a second action gateway.
- Switch and verify exact host, SHA, login, role denial, incident views, audit trails and rollback.

**Exit:** secure independent operator deploy with no privilege drift.

## Phase 5 — extract platform and Octopus

- Move `.octopus`, CI scripts and infra definitions **after** the source repo acceptance process is green and a migration plan exists for all relative paths.
- Pin immutable full component SHAs, dependency versions and image digests. Test component-relevant checks per PR; retain *full* integrated 7-lane release checks with real PostgreSQL/pgvector and no intentional skips.
- Fix worker limits/timeouts rather than mark exit 137 success; use capable approved runners with no unreviewed paid usage.
- Switch Octopus project Git/source after checking configuration-as-code path, worker pools, triggers, secrets references, release tags, webhook duplication and artifact provenance.
- Keep Drone standby only if explicitly activated; do not resurrect retired CircleCI or Codefresh authority.

**Exit:** reproducible cross-repository release manifests and a green exact-SHA Octopus release with rollback.

## Phase 6 — extract workloads only after service boundaries work

- Move Ruby RAG, Ruby worker, Ruby transport/control, sandbox, model manifests and research assets to one source repo, initially without forcing separate always-on services.
- Require authenticated RPC, least privileges, RAG ownership and rollback schema, pgvector parity, idempotency, bounded retries/queues, sandbox isolation, job cancellation and offline fallback.
- Keep GPU work on Node 001 and compatible work on approved free compute. Do not make tiny web hosts install model weights/Torch/pgvector without resource proof.
- Distinguish `source extracted` from `workload independently deployed`.

**Exit:** worker outage and recovery tests show no duplicate execution, bypass or unbounded resource usage.

## Phase 7 — optional contracts, stabilization, source archive

- Publish `ayahos-contracts` only with multiple consumers and real independent versioning needs.
- Audit GitHub check refs, branch rules, package paths, Cloudflare/Vercel/Render/Cloud Run, Octopus, Supabase, DNS, owner scripts, documentation and user-facing URLs.
- After final cutover, retain prior releases for a recommended 14-day measured stabilization period. Archive source repo only after validated recoverability. Never force-push/delete first.

## Required cross-repo release envelope

Release artifact (not secrets) records:
`release_id`, `environment`, per-component `repository`/`full_sha`/`artifact_sha256`, `schema_version`, `api_contract_version`, `required_checks` with Octopus run IDs, signed/redacted smoke evidence, `rollback_release_id` and recorded approval.

Gates: standalone lint/type/unit => producer-consumer contracts => integrated tests pinned to complete SHAs => security/provenance => preview/canary => authenticated live-safe smoke => explicit promotion => post-release metrics. Policy/auth failure, wrong commit, key exposure, suspicious cost or incomplete CI => **STOP and roll back**.

## Offline migration preflight

`migration/repositories.json` is the planned directory map. Before creating any git history or destination repo, inspect paths and run `python3 scripts/migration/repositories.py` and the tests if the helper has been installed; staging is optional and never deployment. A copy alone is **not** an executable standalone repository. Manually inspect committed and historical secrets, licenses, native dependencies, package lock roots and Git history before any pushes.
