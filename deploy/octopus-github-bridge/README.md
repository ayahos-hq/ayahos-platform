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

The status context is `octopus/verify`. Only pushes to branches of `GITHUB_REPOSITORY` are
verified; forks, tags and branch deletions are ignored. Secrets stay in the Worker and are never
passed into the Octopus process, so code on a branch under test cannot read them. A deployment
started by hand in the Octopus UI is not reported; push again or redeliver the webhook instead.

## Current state (2026-10-21)

The Worker is **deployed** at `https://ayahos-octopus-github-bridge.fuaadabdullah.workers.dev`
and the GitHub webhook (step 7) is **live**. KV, the Octopus values, `OCTOPUS_API_KEY`, and
`GITHUB_WEBHOOK_SECRET` are all configured on the deployed Worker — production values live in
the Worker configuration, not in the committed `wrangler.jsonc` (which still carries the
template placeholders).

**One step remains: step 4.** `GET /healthz` currently answers
`missing configuration: GITHUB_STATUS_TOKEN`. Create the fine-grained token (this repository
only, *Commit statuses: Read and write*, nothing else) and add it to the Worker as the secret
`GITHUB_STATUS_TOKEN` — either `npx wrangler@4 secret put GITHUB_STATUS_TOKEN` or, in the
Cloudflare dashboard: Workers & Pages, `ayahos-octopus-github-bridge`, Settings, Variables and
Secrets, Add, type Secret. `/healthz` must then answer `ok`, and the next push should produce
an `octopus/verify` commit status.

Step 8 (requiring the status on `main`) is **not available on this repository's GitHub plan**
(branch protection and rulesets return 403 for private repos on the free plan), so until the
plan changes the status is advisory: merges are gated by convention, not by GitHub.

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
4. **GitHub token.** Create a fine-grained personal access token for this repository only, with
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
   status check `octopus/verify`.

Do not also add an Octopus Git trigger for this project: it would create untracked releases on
`main` alongside the ones this bridge reports.

To re-run verification for a commit without a new push, redeliver its push event from
Settings, Webhooks, Recent Deliveries.

## Test

`node --test test/*.test.js` (no dependencies). The `web` gate in `scripts/ci/verify.sh` runs it.
