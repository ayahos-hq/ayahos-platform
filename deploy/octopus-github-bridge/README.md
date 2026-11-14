# Octopus to GitHub bridge

**October 23, 2026 update:** GitHub Actions is not the status or backup
scheduler for AyahOS. The dormant
`.github/workflows/octopus-status-relay.yml` and
`.github/workflows/encrypted-database-backup.yml` were retired. The
Cloudflare bridge remains the only commit-status adapter for the Octopus
verification process. The independent encrypted database backup runs as an
**Octopus runbook**, gated on secure recovery approval. See
`docs/operations/octopus-database-backups.md`. The new runbook still
requires Octopus-side provisioning and a verified task before calling it
active. Historical sections below document the former pilot design.

A Cloudflare Worker that makes the Octopus verification process the merge gate for this
repository. Octopus cannot do this on its own: its Git triggers only follow the default branch of
a version-controlled project, and it posts nothing back to GitHub.

```
GitHub push ──signed webhook──▶ /github ──▶ Octopus: create release on that ref + commit,
                                            deploy to the verification environment
                     ◀── commit status "pending" (links the Octopus task)
cron, every minute ──▶ Octopus GET /tasks/{id} ──▶ commit status success / failure / error
```

The status context is `octopus/verify` (posted only when a token is configured). Only pushes to
branches of `GITHUB_REPOSITORY` are verified; forks, tags and branch deletions are ignored. Secrets stay in the Worker and are never
passed into the Octopus process, so code on a branch under test cannot read them. A deployment
started by hand in the Octopus UI is not reported; push again or redeliver the webhook instead.

## Current state (2026-10-22)

The Worker is **deployed** at `https://ayahos-octopus-github-bridge.fuaadabdullah.workers.dev`
and the GitHub webhook (step 7) is **live**. KV, the Octopus values, `OCTOPUS_API_KEY`, and
`GITHUB_WEBHOOK_SECRET` are all configured on the deployed Worker — production values live in
the Worker configuration, not in the committed `wrangler.jsonc` (which carries the verified
non-secret Octopus values plus placeholders for the KV id and environment name).

**The optional-token code is now deployed** (status: *implemented*; *verified-live*
2026-10-22): the code-only redeploy landed and `GET /healthz` answers `ok` (Worker version
`af099a2e`), with all production config surviving untouched. `GET /status/<sha>` answers as
documented below.

**`GITHUB_STATUS_TOKEN` is not set yet** (provisioning in flight, parked on the owner's
GitHub Mobile approval). Until it is set with `wrangler secret put GITHUB_STATUS_TOKEN`, no
`octopus/verify` commit status is posted: verification outcomes are only readable at
`GET /status/<sha>`. Once the token lands, prove the loop with a test push and confirm the
`octopus/verify` status actually appears on the commit. A GitHub Actions job that turns
`/status` into a check is *planned*, not present; `AGENTS.md` forbids new workflows without
an architecture decision.

Step 8 (requiring the status on `main`) is **not available on this repository's GitHub plan**
(branch protection and rulesets return 403 for private repos on the free plan), so until the
plan changes the status is advisory: merges are gated by convention, not by GitHub.

## Octopus environment mismatch (observed 2026-10-23 UTC)

The signed webhook and Octopus release-creation request succeeded, but the Octopus
deployment endpoint rejected a verification run with HTTP 400:
`Unable to locate deployment environment(s) named 'Verification'`.
This is an **external environment configuration failure**, not a passing or failing
repository test. No test task was created. The bridge now queries the names of
configured environments on that exact error, logs only sanitized names through
private Cloudflare observability, records `octopus/verify=error`, and refuses
to substitute a production environment or create a new environment implicitly.
A read-only environment listing performed with the deployed service credential on
2026-10-23 returned **Development** as the single permitted environment.
This is the selected existing non-production verification destination; no new
Octopus environment is created and no production targets are selected.
Set `OCTOPUS_ENVIRONMENT` only to a verified, project-accessible non-production
environment whose lifecycle permits the eight required CI steps.

The deployed Worker currently has a managed `GITHUB_STATUS_TOKEN` binding and is
able to record GitHub error statuses. This resolves the *missing status writer*
but does not resolve deployment environment configuration or prove the gates.
Do not copy any secret values into source or diagnostic output.

## `GET /status/<sha>`

Unauthenticated and read-only. It is safe to expose only because a 40-hex commit SHA is not
guessable, and it returns nothing but the state: no Octopus error text, task link or branch name.
A caller who already knows a SHA can learn whether it was verified and how it ended; nothing else.

| Response | Meaning |
| --- | --- |
| `200 {"sha", "state"}` | `state` is `pending`, `success`, `failure` or `error` |
| `404` | no usable record: the commit was never verified, the push has not been processed yet (the record appears only after Octopus accepts the release), or the 7-day record expired. Treat as "not yet" and poll for a bounded time |
| `400` | not a lowercase 40-hex SHA |
| `503` | the bridge is missing required configuration (see `/healthz`) |

Every response is `Cache-Control: no-store`. Only `GET` on the exact path is answered. The latest
state wins, so redelivering a push resets that commit to `pending`. Forks, tags and deletions are
never verified. `success` means the commit's *own* process passed: Octopus resolves the process and
its gate scripts from the pushed commit, so the verdict is only as trustworthy as whoever can push
to this repository. CODEOWNERS cannot be enforced on this plan.

## Set up (once)

Run from `deploy/octopus-github-bridge/`.

1. **KV namespace.** `npx wrangler@4 login`, then `npx wrangler@4 kv namespace create TASKS`, and
   put the printed id into `wrangler.jsonc`.
2. **Octopus values.** In `wrangler.jsonc` set `OCTOPUS_URL` (for example
   `https://<instance>.octopus.app`), `OCTOPUS_SPACE_ID` (for example `Spaces-1`),
   `OCTOPUS_PROJECT` (the project name) and `OCTOPUS_ENVIRONMENT` (the environment the
   verification deployment goes to; it must be in the default channel's lifecycle).
3. **Octopus API key.** Create a service account (Configuration, Users, Create service account)
   in a team whose role allows `ProjectView`, `ReleaseCreate`, `DeploymentCreate` and `TaskView`,
   scoped to this project and the verification environment. Create an API key for it, then
   `npx wrangler@4 secret put OCTOPUS_API_KEY`.
4. **GitHub token (optional; required for the `octopus/verify` commit status).** Create a
   fine-grained personal access token for this repository only, with
   *Commit statuses: Read and write* and nothing else, then
   `npx wrangler@4 secret put GITHUB_STATUS_TOKEN`.
5. **Webhook secret.** Generate one (`openssl rand -hex 32`), then
   `npx wrangler@4 secret put GITHUB_WEBHOOK_SECRET`.
6. **Deploy.** `npx wrangler@4 deploy`. `GET https://<worker-host>/healthz` must answer `ok`;
   otherwise it lists the missing settings by name.
7. **GitHub webhook.** Repository Settings, Webhooks, Add webhook: payload URL
   `https://<worker-host>/github`, content type `application/json`, the secret from step 5,
   *Just the push event*. GitHub's ping must get `pong`.
8. **Merge gate.** Repository Settings, Rules (or Branches), the rule for `main`: require the
   status check `octopus/verify`. This only works when step 4's token is set, since that is what
   posts the check.

Do not also add an Octopus Git trigger for this project: it would create untracked releases on
`main` alongside the ones this bridge reports.

To re-run verification for a commit without a new push, redeliver its push event from
Settings, Webhooks, Recent Deliveries.

## Test

`node --test test/*.test.js` (no dependencies). The `web` gate in `scripts/ci/verify.sh` runs it.

## Branch-scoped queue coalescing (opt-in, 2026-10-23)

`BRANCH_QUEUE_ENABLED=true` (a **nonsecret** Cloudflare Worker setting) enables an
existing-KV-only, tokenless scheduling path. The default is **off**, preserving
the deployed bridge until the implementation is verified and separately promoted.
When enabled:

1. A signed, validated GitHub push stages only the newest *observed* SHA per
   branch in the `TASKS` KV namespace. Repeated delivery of the same SHA is
   idempotent. A staged SHA is **unknown**, not pending or green, at `/status`
   until Octopus actually accepts a release.
2. The Worker receives a cron trigger every minute but, when this feature is
   enabled, performs its task reconciliation and queue scan **only once every
   six minutes**. It waits at least 90 seconds after the last observed push on
   that branch. It starts **at most one new Octopus release per six-minute batch**.
   A task already recorded for that branch must complete before another is
   started. No running or queued Octopus task is canceled; other branches are
   isolated. Consecutive pushes coalesce before a release is created.
3. Per-SHA attempts are bounded at two, with a two-minute backoff. Failure to
   start is never treated as a passing gate. Scheduling stops conservatively
   when KV task/branch enumeration exceeds the bounded limits.
4. On this path, an existing `GITHUB_STATUS_TOKEN` binding is **ignored**
   for both task polling and task creation. Read the actual verdict through
   `GET /status/<sha>`; an Octopus task log must still prove **all eight**
   gates on the exact SHA for release acceptance.

**Backlog fairness:** the original task reconciler always inspected only
the first 20 lexicographically listed `task:` keys. With more than 20 queued
Octopus jobs, long-running earlier tasks permanently starved later SHAs, so
their `pending` verdicts could not advance even if Octopus finished.
The reconciler now saves an opaque `meta:reconcile_cursor` in the existing KV
and rotates through pages on successive scheduled batches. It retains a
failed/pending task until Octopus itself confirms a terminal state. Cursor
advancement is best effort under KV eventual consistency; temporary duplicate
reads or deferred tasks are acceptable, invented passing results are not.
Task reconciliation remains capped at 20 Octopus GET calls per batch.
The cursor adds at most one KV key write/delete per six-minute scheduled batch
when page position changes, roughly 240 writes/day in the worst case.
Do not delete tasks to make the queue seem empty.

**Production cron resolution (2026-10-23):** The legacy Worker was triggered once per minute even without the branch-queue feature flag. Its one task-list call per minute consumed 1,440 KV list operations/day, above the KV Free plan's 1,000 daily allowance. Set the live Worker cron and `wrangler.jsonc` to `*/6 * * * *`: 240 task lists/day, cursor rotation across queued pages, immediate webhook launches unchanged, GitHub status writer remains enabled. Do not turn on tokenless branch coalescing until the GitHub status propagation contract is independently verified. A passing Octopus run, not a KV 'pending' record, remains the acceptance gate.

**Free-tier limit:** Cloudflare Workers KV Free currently allows 1,000 list
operations per day. The legacy cron (one task list per minute) requires up to
1,440 lists/day even without this extension. The opt-in scheduler batches
every six minutes, consuming at most **3 × 240 = 720 lists/day** from its
reconcile/task/desired enumerations, leaving headroom for other operations.
The new path may delay a status transition by up to six minutes. Never set
up an additional per-minute polling Worker for this task.

**Correctness caveat:** Workers KV is eventually consistent, not transactional.
This is **best-effort** burst reduction, not a distributed lock, a guarantee
against simultaneous duplicate deliveries, or a substitute for true task
serialization. Never use it as a reason to mark an unknown, canceled, failed
or merely queued commit as successful. For strict cross-region atomic
deduplication, a separately reviewed Durable Object or equivalent
single-writer service is required. Do not introduce one without checking the
free-tier budget and infrastructure ownership.

**Deployment:** Do **not** deploy from the checked-in `wrangler.jsonc`:
it intentionally contains an invalid production KV namespace placeholder.
A separately authorized release must deploy the exact reviewed code using
the *live Worker settings and existing KV/secret bindings*, then set the
nonsecret `BRANCH_QUEUE_ENABLED=true`. First confirm the complete focused
test suite (`node --test test/*.test.js`) and the real Octopus task result.
Observe live cron logs, task count, and `GET /status/<sha>` before considering
the scheduler active. Set `BRANCH_QUEUE_ENABLED=false` to roll back to the
legacy eager-verification behavior without changing secrets or deleting tasks.

This opt-in does not retroactively cancel or delete the existing Octopus
backlog. Avoid unnecessary branch pushes while it drains.
