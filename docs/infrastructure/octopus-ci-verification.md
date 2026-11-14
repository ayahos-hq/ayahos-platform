# Octopus required CI gates

## October 28, 2026 — Production live-chat acceptance (candidate)

The version-controlled deployment process adds **one required Production-scoped**
step after the eight existing source-verification steps. Development and Staging
retain the original eight steps. The new step invokes
`scripts/ci/octopus_verify.sh live-chat` on the existing hosted Ubuntu
execution container; it runs `scripts/ci/live_chat_gate.py` with
`EXPECTED_SHA` derived from the exact Octopus Git release revision.

This is a **real inference** gate, not a browser fixture: it verifies
`/api/build` reports the expected full main commit, then sends one bounded JSON
chat request and one streaming SSE request through
`https://ayahos.pages.dev/api/chat`. Acceptance requires HTTP 200, the
correct response content type, nonempty completed model output, and a terminal
SSE `done` event. A missing or different commit, provider failure, incomplete
stream, missing environment evidence, or timeout returns a nonzero exit code.
No API secrets are required; results are text-free
`artifacts/live-chat-gate.json` evidence.

**Execution and scope:** Octopus remains the authoritative process. This step
runs only when an Octopus release is explicitly deployed to the **Production**
environment; a successful Development verification task or a Cloudflare preview
does not execute it. The Octopus bridge currently targets Development, so it
must **not** be described as an automatically running production gate. Fly and
Cloudflare must already have deployed the same commit before the Production step
runs. This gate blocks Production acceptance but **does not automatically roll
back Fly or Cloudflare**. A failed gate must be followed by a separately
authorized deployment rollback to the previous verified artifacts.

**Observed prior to merge (2026-10-28 21:17 UTC):** A local invocation against
production commit `b7986c9818efe24036535f4fc7eed4d98f4cda3e` returned
`PASS`: build SHA (119 ms), JSON via provider `node-001` (2,590 ms), SSE
(1,504 ms, two nonempty delta events). Total 4,214 ms. This proves the
standalone probe, not the new Octopus Production step. Octopus still requires
a new exact-commit release/task after merge for the deployment-process change
to be verified on its hosted worker.



## October 28, 2026 - CI container Ruby compatibility correction

Octopus task `ServerTasks-4401` for PR #450 (commit `d18c8d28`) passed all seven source-verification stages, then **failed the deployable image build**: the `python:3.15-slim-bookworm` base supplied Ruby 3.1.2, while the Ruby RAG/Control Gemfiles require Minitest 6 and Ruby 3.2+. The scoped fix switches the **CI deployable container only**, not Fly's production image, to a digest-pinned `python:3.15-slim-trixie` base with Ruby 3.3. This does not change the existing Octopus acceptance authority or production credentials.

On the isolated Ubuntu Linux Docker host, the corrected image built successfully. The existing `scripts/ci/deployable-container-smoke.sh` returned **exit 0**, exercising health, RAG ingestion and retrieval; startup `curl` retries returned transient connection reset/503 before readiness. The repository-wide `scripts/ci/tests` suite ran **40 tests, all passed** on Linux. A new regression test asserts the compatible, digest-pinned base. A fresh exact-SHA Octopus hosted-worker task remains required before merging.

## Documentation checkpoint — 2026-10-25 — distinguish monorepo acceptance from HQ Development

The **existing monorepo Octopus release authority** remains separate from the newer **HQ Verification Development-only** project. [Merged HQ Platform PR #34](https://github.com/ayahos-hq/ayahos-platform/pull/34) documents exact-SHA five-repo acquisition on Linux and a passing HQ Development release **0.0.18 / Deployments-351** with **three required source checks**. This is real, narrowly scoped source-assembly evidence; it does **not** mean the eight-step monorepo gate passed for the latest monorepo SHA, nor that HQ image artifacts, OCI manifests/digests, real pgvector/restore, staging auth or production canary passed. The isolated composite artifact builder is still under review in [HQ Platform PR #36](https://github.com/ayahos-hq/ayahos-platform/pull/36).

Never attach an HQ green badge to the incumbent monorepo `octopus/verify` status or infer status posting from a successful webhook ping. Inspect exact platform and component commits, Octopus release/task logs, required steps, image digests and post-deploy probes independently before promotion. Some earlier dated sections here predate the HQ Development source verifier; retain them only as historical evidence.


## October 23, 2026: GitHub Actions retirement for AyahOS operations

**Octopus is the only CI and backup orchestration provider.** Merged source
replaces the experimental GitHub Actions encrypted-backup dispatcher with
`.octopus/runbooks/encrypted-database-backup.ocl` and
`scripts/ci/octopus_db_backup.sh`. The distinct Octopus runbook uses a
dedicated backup worker and sensitive values restricted to the runbook;
eight standard CI verification steps remain unmodified and secrets-free.
An operator must register/provision the dedicated Octopus backup worker,
sensitive runbook variables and Config-as-Code runbook discovery in Octopus
before this source can execute. **No live runbook task has been verified.**
Refer to `docs/operations/octopus-database-backups.md`.

The inactive GitHub Actions Octopus-status-relay experiment is removed as
well; the Cloudflare Octopus GitHub bridge remains the status reconciliation
authority. A GitHub status (or missing status) does not replace a successful
Octopus task tied to the exact SHA. Do not reinstate an Actions workflow
because status posting is intermittently unavailable.


**Primary acceptance configuration:** `.octopus/deployment_process.ocl`
uses Octopus Configuration as Code, and its eight steps are marked
`is_required = true`. The processes run serially: a failed preceding step
prevents false release acceptance.

| Required step | Source script argument | Validation |
| --- | --- | --- |
| api-postgres | `api` | API Ruff, mypy, tests, sandbox tests, PostgreSQL migrations |
| web-site | `web` | web/site tests, lint, type-check, builds |
| ml-cpu | `ml` | CPU model dependencies and MiniLM test smoke |
| rag-postgres | `rag` | Ruby RAG, genuine PostgreSQL and pgvector |
| ruby-worker | `worker` | Ruby delivery and Python contract integration |
| ruby-control | `control` | Ruby gateway tests |
| release-hardening | `release` | Mandatory release gates with no skipped tests |
| deployable-container-smoke | — | Builds the root Dockerfile, boots the colocated Ruby/Python image, and exercises health plus RAG |

All scripts resolve from the *Octopus project Git revision*, and all
PostgreSQL tests are scoped to an ephemeral local database created inside
an Ubuntu 24.04 worker-tools container. The `vector` extension is required,
not silently skipped. A non-container host or incompatible operating
system is rejected before dependency installation.

The database is provisioned inside each worker, so the required Octopus
verification lanes do not need a `TEST_DATABASE_URL` or database credential
project variable. The setup script refreshes APT once per worker, installs
only the runtimes needed by that lane, and checks PostgreSQL readiness before
Ruby dependency resolution so hosted worker timeouts surface as actionable
setup failures instead of killing a late readiness probe.

## Diagnosing a hosted-worker exit 137

Exit 137 means a process received SIGKILL. It does **not** by itself prove an
out-of-memory kill; Octopus, Docker, or the underlying worker may also terminate
a process due to a deadline or external cancellation.

The RAG lane prints `CI_RESOURCE` snapshots before and after Ruby setup,
PostgreSQL provisioning, and the required pgvector tests. On cgroup v2 the
snapshots include `memory.current`, `memory.max`, `memory.peak`, and
`memory.events` (`oom` and `oom_kill` counters) without printing environment
values or secret URLs. If the entire container is killed, the **last completed**
snapshot is all that can be retained. Look for increases in `oom_kill` across
snapshots and compare the final log timestamp to Octopus step/task limits.
A counter of zero does not rule out a worker-level or parent-cgroup OOM.

To reduce peak consumption, only the *ephemeral RAG test PostgreSQL cluster*
uses 32 MB shared buffers, 2 MB work memory, 16 MB maintenance memory, and no
parallel PostgreSQL workers. The RAG Bundler install runs one job at a time.
The genuine PostgreSQL 16 `vector` extension remains mandatory: no tests
are skipped, no SQLite substitute is accepted, and no credentials are changed.

If repeated exit 137 events coincide with rising OOM counters even after
these limits, use an appropriately sized worker/container or a separate CI
runner for the RAG gate. Do not mark the release green or disable RAG/pgvector
to work around insufficient resources. A fresh Octopus release run on the
patched Git revision is still required to verify hosted-worker behavior.

The process uses the current project Git source, worker-pool slug
`hosted-ubuntu`, and Docker feed slug `docker-hub-public`. The actual
Octopus project must have these resources configured. The seven execution-container steps pin `octopusdeploy/worker-tools:6.6.5-ubuntu.24.04` instead of
tracking the mutable `ubuntu.24.04` tag. Docker Hub lists this published version
for Ubuntu 24.04. The tagged image has **not** been exercised by AyahOS Octopus;
verify the worker architecture, available Node tooling, and exact image digest
on the first real run, then pin the digest for stronger immutability.

## Verify on the live Octopus project

1. Confirm Octopus project Version Control points to
   `fuaadabdullah/AyahOS_Dual_Lineage` with base path `.octopus`.
2. Confirm the hosted Ubuntu worker pool can use Docker execution
   containers and the Docker Hub external feed exists.
3. Select the exact merged SHA in the Octopus Git-backed release, create
   the release, and execute it in the verification environment.
4. Inspect the actual Octopus task log: all eight required steps, each on that
   SHA, no failed, disabled, or skipped steps. Inspect test counts and
   PostgreSQL/pgvector evidence; do not accept a no-op release.
5. Confirm a push or PR actually triggers Octopus, if intended, and
   correctly publishes the GitHub acceptance status. Octopus
   version-controlled process files do not automatically create a trigger.
6. Keep production rollout separate. A passing synthetic or unit
   verification process is not authenticated live inference or rollback
   proof; those require separate E2E probes.

## Triggering and GitHub status

Octopus Git triggers only follow a version-controlled project's default branch, and Octopus
posts nothing to GitHub, so neither pull requests nor `main` get a result on their own. The
[Octopus to GitHub bridge](../../deploy/octopus-github-bridge/README.md) closes that gap: a signed
GitHub `push` webhook makes it create a release on the pushed branch and commit and deploy it to
the verification environment, and a cron trigger reports the task outcome as the commit status
`octopus/verify` when `GITHUB_STATUS_TOKEN` is configured. On private GitHub Free, repository rulesets/branch protection may be unavailable, so an advisory status is not a GitHub-enforced merge gate. Without
the token (it is optional) no commit status is posted; the outcome is only readable, read-only and
unauthenticated, at `GET /status/<sha>` on the Worker. Its setup steps (KV namespace, Octopus
service account key, GitHub token, webhook, branch rule) need the owner's accounts.

## Post-deploy live verification

The seven gates above verify a commit. They say nothing about the deployed
stack. After Render deploys `main`, run the `live` lane
(`scripts/ci/octopus_verify.sh live`, which calls `scripts/ci/post-deploy.sh`)
with Octopus variables `EXPECTED_SHA` (the deployed commit),
`LIVE_RUNTIME_API_KEY` and `LIVE_SITE_API_KEY`. It waits for the live web and
API to attest that SHA, runs the authenticated live E2E, then the release
smoke and evidence publication, and fails closed on any HOLD. Evidence lands
in `artifacts/`. This lane is deliberately not one of the seven required
steps and is not a merge gate.

For a secrets-free timer check, `scripts/ci/canary.sh` exercises the public
site and public chat path only.

**Audit update (2026-10-23 00:13 UTC):** The connected Cloudflare API confirms the deployed bridge has `GITHUB_WEBHOOK_SECRET`, `OCTOPUS_API_KEY` and a `TASKS` KV binding, but **no `GITHUB_STATUS_TOKEN` secret**. A KV key listing returned zero task/result keys at inspection. That is absence of recorded tasks in that namespace, not proof that Octopus never ran. GitHub `main` reports `protected:false`; only Cloudflare Pages and Vercel checks were visible for commit `fe7586f` and neither is an Octopus acceptance result. Render reported both the API and admin deployments of `fe7586f` as live, but this does not verify authenticated chat, pgvector RAG or Octopus.

Until a valid status writer exists and `octopus/verify` is enforceable, require a **human review of exact SHA, Octopus task log, eight required steps, test evidence, plus post-deploy smoke** before treating any behavioral release as accepted. A 200 from the Worker `/healthz` only means mandatory webhook/Octopus settings are present; it does **not** prove commit-status capability because that token is intentionally optional in `missingConfig`. Do not invent a passing status or relax the gates.

Octopus reference documentation:
- https://octopus.com/docs/projects/version-control/ocl-file-format
- https://octopus.com/docs/projects/steps/execution-containers-for-workers

## Verification environment repair (2026-10-23 UTC)

Cloudflare Worker logs confirmed release creation succeeded but Octopus rejected the
`deployments/create/untenanted/v1` call with HTTP 400 because no accessible environment
was named `Verification`. The authenticated service credential subsequently listed
`Development` as its sole authorized environment. The bridge is to use `Development`
for CI-only worker execution, keeping the eight mandatory steps unchanged. This
is **not** permission to use staging/production deployment targets or claim a
successful release; accept only exact-SHA Octopus task success after the change.

**Bridge repair evidence:** Cloudflare Worker version `0ff7a5bb-1373-4968-aa94-bbd295299b68`
was observed live at 100% with `OCTOPUS_ENVIRONMENT=Development` and all
three managed-secret binding names plus the existing KV namespace preserved.
These settings establish only the bridge configuration, **not** an accepted
Octopus test task. No credential values were read or committed.

## CI cancellation policy (2026-10-23)

`cancel_queued_tasks = false` and `cancel_running_tasks = false` are
**both** required for our shared CI-only project and Development environment.
Octopus's queued-task supersession is scoped to project/environment/tenant,
**not to Git ref**. With `cancel_queued_tasks = true`, a push on another
feature branch silently cancels the older queued exact-commit verification
before any of its eight required checks can start. We reproduced this:
`ServerTasks-1195` (PR #343, `3b45c9f`) was queued, and after another
branch push its outcome changed to `error: Octopus task was canceled`.
Earlier settings also canceled running tasks. Both policy switches must
be disabled to preserve per-commit test acceptance across branches.

**Free-tier tradeoff:** a burst of pushes can now accumulate legitimate
eight-step verification tasks. Monitor queued count, execution minutes,
and task age; do not automatically fan out reruns or delete distinct
pending SHAs. Implement branch-scoped deduplication with an explicit
latest-revision handoff in the existing bridge before reinstating any
cancellation policy. For now prefer small sequential batches, not
multiple concurrent branch pushes. An overdue/pending/canceled task is
never green and cannot authorize a behavioral merge.

This is a CI scheduling configuration fix, not test success, extra
resources, reduced coverage, provider routing, or a production deployment.
The live Octopus project's settings may lag Git-backed OCL; verify actual
`CancelQueuedTasks=false` and `CancelRunningTasks=false` in the live
project before claiming the fix is active.
