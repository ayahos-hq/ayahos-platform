# Octopus to GitHub bridge

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

## Current state (2026-10-23)

The existing Worker is live at
`https://ayahos-octopus-github-bridge.fuaadabdullah.workers.dev`. Its configured repository is
`fuaadabdullah/AyahOS_Dual_Lineage`, environment is `Development`, and its Octopus project
`AyahOS` uses that monorepo as its Git source. The encrypted `OCTOPUS_API_KEY` and
`GITHUB_WEBHOOK_SECRET` bindings are present. After rotating the webhook secret, pings from
both the monorepo and `ayahos-hq/ayahos-platform` received HTTP 200. A successful ping proves
signature transport only: the Worker intentionally ignores HQ pushes because they do not match
its configured repository. `GET /healthz` returned `ok`; no HQ Octopus release or passing
`octopus/verify` status was established.

**Do not deploy this `wrangler.jsonc` as-is or repoint the existing Worker to HQ.** Its KV ID
and environment are placeholders, and repointing would interrupt the monorepo's release path.
The HQ platform repository needs a separate Octopus project connected to
`ayahos-hq/ayahos-platform`, a process whose checks fetch the manifest-pinned component SHAs
rather than assuming a monorepo checkout, and a separate bridge/Worker with its own KV and
scoped credentials. Configure the HQ webhook to that new endpoint only after the project and
bridge are ready. Sealed secrets from the existing Worker cannot be copied out of Cloudflare;
provision new scoped values directly in the new Worker. Until then, `/status/<sha>` on the
existing endpoint is **not** HQ release evidence.

This public HQ repository does not currently have an enforceable required-check gate. Keep
manual review of exact-SHA Octopus evidence before any merge or cutover.

## `GET /status/<sha>`

Unauthenticated and read-only. A commit SHA may be public or discoverable; the endpoint
therefore returns only the state, with no Octopus error text, task link or branch name.
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
