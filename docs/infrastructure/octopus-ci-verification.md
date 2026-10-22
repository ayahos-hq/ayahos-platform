# Octopus required CI gates

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
Octopus project must have these resources configured. The seven steps pin `octopusdeploy/worker-tools:6.6.5-ubuntu.24.04` instead of
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
4. Inspect the actual Octopus task log: seven required steps, each on that
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
`octopus/verify` when `GITHUB_STATUS_TOKEN` is configured. Require that status on `main`. Without
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

**State at code authoring:** The repo configuration is changed and tests
are added; Octopus execution and GitHub status reporting are *unverified*.
CircleCI/Vercel checks are not Octopus evidence.

Octopus reference documentation:
- https://octopus.com/docs/projects/version-control/ocl-file-format
- https://octopus.com/docs/projects/steps/execution-containers-for-workers
