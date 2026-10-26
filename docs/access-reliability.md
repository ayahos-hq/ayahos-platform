# AyahOS HQ access reliability and authority boundaries

**Scope:** Read-only diagnosis and documented one-time authorization, not a standing
admin grant. Source observations were collected 2026-10-25/26 and must be rechecked
before use. The existing monorepo production bridge and Octopus release authority
must remain independent from the proposed HQ promotion path.

## Observed failure modes

| Surface | Evidence at checkpoint | Correct interpretation |
| --- | --- | --- |
| GitHub | `gh auth status` was authenticated as `fuaadabdullah` and could access HQ repositories | Local GitHub CLI is available; this does not authorize all GitHub App, Cloudflare, or Octopus operations |
| Cloudflare | Local `wrangler whoami` selected the **GoblinOS/ForgeTM** account, while the failing HQ Workers Builds details URL identified a **different account** | Wrong account context, not evidence that the HQ Worker was deleted; do not re-create it or deploy the monorepo bridge in its place |
| Wrangler OAuth | The original named-profile flow failed on a localhost callback timeout. Wrangler 4.152 supports `login --device`, confirmed on the connected desktop. | Use **isolated** `XDG_CONFIG_HOME` plus the device authorization grant; an iPhone can approve the code without forwarding localhost callbacks. The account owner still must approve access. |
| Octopus | `octopus space list` displayed a login banner rather than authenticated JSON | Local Octopus CLI is not an authenticated diagnostic source, even if a GitHub status links to an Octopus task |
| HQ Workers Builds | Cloudflare posted a failed Worker build on Platform PR #37 and other platform commits | Need **owning-account** build logs before editing root-directory, Worker name, deploy command, token or Git connection. Do not assume a particular root cause |
| Monorepo | Ruff import-order repair in #419 was merged after an authoritative passing Octopus check; #421 has a separate pending exact-SHA gate | Passing one PR does not transfer acceptance to another SHA |

## Verified after owner approval (2026-10-26 UTC)

The owner completed Cloudflare OAuth device authorization on the connected
Windows host. The separately isolated `wrangler whoami` now enumerates the
**AyahOS_HQ** account, and `wrangler deployments list --name
ayahos-hq-verification-bridge` succeeded with that explicit account. The
personal Wrangler default profile still enumerates GoblinOS/ForgeTM and was
not overwritten. The access doctor originally produced a Windows false
negative because Python's `subprocess` did not resolve the npm
`wrangler.CMD` shim automatically. The fix resolves the exact executable
with `shutil.which` and invokes it without a shell; 11/11 isolated tests
and platform source/manifest checks passed, and the local helper was updated.

**Remaining least-privilege gap:** Cloudflare's Workers Builds log REST endpoint
returned HTTP 403 / code 12004 even though Worker deployment-list access
succeeded. This is a separate **Workers CI Read** authorization boundary, not
proof that the Cloudflare identity is wrong. Inspect logs using an authorized
dashboard session or a user-scoped Workers CI Read token provisioned directly
in Cloudflare's secret store; never paste tokens into chat or public CI output.
The exact failing build root cause remains unverified. Local Octopus CLI
authentication is still absent, and production release checks remain mandatory.

### Cloudflare Workers Builds misrouting (observed 2026-10-26)

The authenticated Chrome account `AyahOS_HQ` exposed Worker Build
`28089f23-2e02-4755-8bbc-138bdfea23ba` for
`ayahos-hq-verification-bridge` (Platform PR #38,
commit `1974930b9b5fe14c9e1b86d4d6814a755df2c8cb`).
Its configured **build command forcibly checks out**
`feat/pinned-hq-artifact-assembly-20261025` after Cloudflare clones the
requested PR commit. The build therefore cannot validate that PR's exact
source SHA. The root `/deploy/octopus-github-bridge` has
`wrangler.jsonc` with a DIFFERENT Worker name:
`ayahos-octopus-github-bridge`, placeholder production TASKS KV ID and
empty Octopus environment. The preview command is
`npx wrangler preview`. **Do not run `wrangler deploy` or repoint
the existing Worker to this unrelated config.**

Read-only desktop CLI reproduced the distinction:

- `wrangler deploy --dry-run` from the committed bridge directory
  succeeded for JS bundling, **but** explicitly reported
  `TASKS=REPLACE_WITH_KV_NAMESPACE_ID` and empty
  `OCTOPUS_ENVIRONMENT`. Local compilation is **not** deploy safety.
- Read-only deployed Worker retrieval produced a **bundled JavaScript**
  SHA256 `f3162fe8598d81697a531095c63ffb98030ba16a3e37e9bd084fecc6a4130a2c`.
  The raw source in `deploy/octopus-github-bridge/src/worker.js` has a
  different hash, as expected for unbundled source, **but** Wrangler 4.152
  `deploy --dry-run` from that source produced exactly the same bundle hash.
  The code lineage is reconciled; the **separate bindings/Worker identity**
  remain a hard safety boundary. The raw-source-versus-bundle hash difference
  is *not* a source divergence.
- Local `wrangler init --from-dash` invoked Create Cloudflare and generated
  a generic starter app; the CLI invocation ended with an error and explicitly
  answered **no deploy**. That scaffold is neither deployed nor source
  authority; never promote it.
- Cloudflare Worker Builds REST log endpoint returned **403 / 12004** with
  the otherwise authenticated Wrangler OAuth token. Read the full failure log
  in the authenticated dashboard or obtain approved, scoped user-token
  **Workers Builds Configuration** access, rather than escalating the
  existing OAuth token indiscriminately.

**Remediation gate:** Preserve existing deployed Worker and its secrets.
First recover the true Worker source/config through authorized read-only
inspection; select the verified HQ Worker-specific source directory, not
the monorepo Octopus bridge. Remove the forced `git checkout` from the
Workers Builds command and validate `WORKERS_CI_COMMIT_SHA` against the
source checkout. Ensure production/preview commands name the exact
verification Worker and that preview variables/bindings are configured
separately; test an isolated exact-commit preview before touching a
production deployment. Never convert a failing CI check to optional,
disable checks or silently bypass an Octopus gate.

## Exact-SHA HQ Worker preview repair (verified 2026-10-26 UTC)

On Platform PR #38, commit
`c94d999fa1a9f5f98318678b21b75d0aa28116b6`, added separate
`deploy/hq-verification-bridge/wrangler.jsonc` and a fail-closed
`scripts/ci/check_hq_worker_build.py`. The source manifest now pins
**69 exact immutable platform blobs**, independently checked by
`scripts/verify-platform.py`. No new release/check authority was created.

- Created dedicated preview-only KV namespace
  `ayahos-hq-verification-preview-tasks` (`2b5af79207114dec9989bc1d952c3c9d`),
  distinct from the production TASKS KV
  (`49ce086dc87f4de9a5110e5771907cb3`).
- Wrangler 4.152 initially refused the preview config without an explicit
  `previews` block. Wrote a regression test reproducing the error, added
  `previews.vars` and `previews.kv_namespaces`, and re-pinned every
  changed source file in `SOURCE-PROVENANCE.json`.
- All 5 HQ config tests, 11 access-doctor tests, 26 bridge integration tests,
  immutable source verification and candidate release-manifest checks passed.
- Uploaded an isolated Cloudflare Preview using exact candidate SHA
  `c94d999fa1a9f5f98318678b21b75d0aa28116b6`; immutable
  preview deployment `3f06cbb3-82cd-4af5-80bd-a76e2900a520`.
  The preview URL is
  `https://access-fix-20261026-ayahos-hq-verification-bridge.ayahos-hq.workers.dev`.
  Preview `GET /healthz` intentionally returns **503** because no
  Octopus/GitHub production secrets were copied into Preview;
  live production `GET /healthz` returned **200 ok**. No production
  release was performed. Do not treat this preview as an authenticated
  integration test or an accepted production promotion.
- The existing **hosted Workers Builds** check still fails on the branch
  because its configured build command forcibly checks out another branch
  and points to the monorepo Worker config. The correct *next* settings
  are specified exactly in
  `deploy/hq-verification-bridge/BUILD_COMMANDS.md` and require a
  Workers Builds Configuration-scoped user API token or an authorized
  interactive Cloudflare dashboard edit; the existing Wrangler OAuth
  token receives **403** on both build logs and trigger configuration.
  Do not change production Worker deployment settings or bypass the
  failing GitHub check to manufacture success.

## Credential architecture

1. **Human identity:** Use one named GitHub identity `fuaadabdullah` and an approved Cloudflare HQ membership, with MFA. An organization invitation is safer than circulating a personal account's tokens. No password or OTP is needed in a repository.
2. **Provider-specific local sessions:** Keep `gh` in its existing credential manager. To avoid overwriting the personal default Wrangler profile, run Cloudflare HQ CLI commands with a separate `XDG_CONFIG_HOME` under the authenticated Windows user's `%APPDATA%\\AyahOS\\wrangler-hq`. `wrangler login --device` uses that isolated default configuration; `wrangler login --profile` is **unsupported**, and named-profile login lacks the device flag in Wrangler 4.152. Restrict this directory to the user; keep credentials out of Git, tickets and chat. Confirm membership in the *actual HQ account*. No implicit account switching.
3. **Nonhuman automation:** Prefer provider-managed short-lived/OIDC or restricted service identities. Octopus gets the required scoped identity; GitHub status is signed by the existing approved bridge, not a newly invented CI path. Secrets belong only in the platform's managed secret store. Never put a broad admin token in an LLM prompt, terminal history, public repository, or CI logs.
4. **Separate authority:** A Cloudflare login grants neither production deployment permission nor deterministic Undermind/Action Gateway authority. Inspect access and release acceptance independently.
5. **Least privilege and recovery:** Read-only diagnostics first; explicit approval for mutations. Scope by project/account, audit access, rotate credentials where exposed, and revoke stale principals. Do not extend token lifetime merely to suppress MFA.

## Repeatable local diagnostic (no secrets printed)

Requires Python 3.11+, GitHub CLI, Wrangler >=4.119 for `login --device`, and Octopus CLI. `scripts/hq/access_doctor.py` forces Wrangler into the dedicated HQ config directory by default on Windows. Override with `AYAHOS_CLOUDFLARE_CONFIG_HOME` only for an intentionally separate operator environment.

```sh
python3 scripts/hq/access_doctor.py --cloudflare-account-id YOUR_VERIFIED_32_HEX_HQ_ACCOUNT_ID --json
python3 -m unittest discover -s scripts -p 'test_access_doctor.py' -v
```

The account ID is an **identifier**, not an API token. Pass it through a local
operator command only; do not commit it to this public repository. The doctor
uses exact read-only CLI commands, does not read credential files, suppresses
raw CLI output, and fails closed for an unknown or wrong Cloudflare account.
`ready_read_only` for Octopus proves *space-list access only*, never deploy authority.

### Phone-compatible device authorization (Windows)

```powershell
# These commands run ON THE AUTHORIZED WINDOWS PC, not in this chat.
$env:XDG_CONFIG_HOME = Join-Path $env:APPDATA 'AyahOS\wrangler-hq'
wrangler login --device --browser=false
wrangler whoami
```

Visit the one-time URL shown by the CLI **on your phone** and approve the
time-limited code. Never publish the code, token or redirect callback. On every
subsequent HQ Cloudflare invocation, reuse this exact `XDG_CONFIG_HOME`; without
it Wrangler silently selects the unrelated personal account. The
`tools/ayahos-access-onboard.cmd` and `tools/ayahos-access-check.cmd` launchers
are installed in the **local** HQ workspace, not committed here. Login
credentials reside in the user's local application-data tree, not in Git.

**Caution:** The device authorization proves user login only. If `whoami` still
does not list the account that owns the HQ Worker, the owner must grant the
correct resource membership. Never substitute the existing production
monorepo Worker, alter DNS or weaken CI gates to manufacture access.

### One-time, owner-approved bootstrap

- **GitHub:** `gh auth status` and `gh api user --jq .login`. If the wrong identity is active, use `gh auth switch` / `gh auth login` interactively. Do not create a new broad PAT.
- **Cloudflare:** The HQ account owner opens the **specific** `ayahos-hq-verification-bridge` Worker and selects **Invite**. Start with **Metadata Read-Only** (settings, logs, traces) scoped to this Worker, promoting to Content Read-Only only if necessary to debug the build; use Editor only for a separately approved deployment. Cloudflare supports individual-Worker roles, so account-wide administrator access is unnecessary. After membership is accepted, run the **isolated device flow** below on the authorized desktop (or `tools/ayahos-access-onboard.cmd` in the local HQ workspace). Approve the short-lived device code from the owner's phone. Verify that **this isolated** `wrangler whoami` can enumerate the owning account and then check the specific Worker is readable. Keep the personal default profile untouched. If an old exposed token exists, revoke/rotate it; never reuse a token pasted into chat.
- **Octopus:** Run `octopus login` locally against the known `https://ayahos.octopus.app` service via the CLI's interactive secure flow. Grant a scoped TaskView/ProjectView identity for diagnostics, not permanent cross-project deployment/admin rights. Run the doctor again and confirm an authenticated response.
- **Workers Builds:** After HQ-account read permission is verified, inspect the exact failed Build ID under **Worker > Deployments > Build history**, then only change the proven misconfiguration. Cloudflare documents root directory, Wrangler `name`, `account_id`, and stale build tokens as distinct possible failure classes. Changing the repo to point to the incumbent monorepo bridge is prohibited.

## Ownership and gate rules

The provider dashboard, ChatGPT plugin, local desktop CLI and hosted CI Worker
have **different sessions**. A successful login to one is never evidence of access
to another. Maintain independent time-stamped access facts and reject undocumented
fallbacks. A status of `ready` never proves live release health, and an Octopus
queue state never proves a passed gate. Do not bypass the failed Cloudflare check
or pending `octopus/verify` to merge production-related PRs.

Official references:
- https://developers.cloudflare.com/changelog/post/2026-09-21-invite-members-to-workers/
- https://developers.cloudflare.com/workers/authorization/workers/
- https://developers.cloudflare.com/workers/wrangler/commands/general/
- https://developers.cloudflare.com/changelog/post/2026-08-04-wrangler-login-device-flow/
- https://developers.cloudflare.com/workers/ci-cd/builds/configuration/
- https://developers.cloudflare.com/workers/ci-cd/builds/troubleshoot/
- https://octopus.com/docs/octopus-rest-api/cli/octopus-login
