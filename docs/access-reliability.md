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
| Wrangler OAuth | Creating a separate named HQ profile initiated desktop-browser OAuth but expired without completing | Owner must complete the callback on the authorized desktop; an iPhone session cannot silently finish the desktop localhost callback |
| Octopus | `octopus space list` displayed a login banner rather than authenticated JSON | Local Octopus CLI is not an authenticated diagnostic source, even if a GitHub status links to an Octopus task |
| HQ Workers Builds | Cloudflare posted a failed Worker build on Platform PR #37 and other platform commits | Need **owning-account** build logs before editing root-directory, Worker name, deploy command, token or Git connection. Do not assume a particular root cause |
| Monorepo | Ruff import-order repair in #419 was merged after an authoritative passing Octopus check; #421 has a separate pending exact-SHA gate | Passing one PR does not transfer acceptance to another SHA |

## Credential architecture

1. **Human identity:** Use one named GitHub identity `fuaadabdullah` and an approved Cloudflare HQ membership, with MFA. An organization invitation is safer than circulating a personal account's tokens. No password or OTP is needed in a repository.
2. **Provider-specific local sessions:** Store `gh` authentication in its existing credential manager and each `wrangler` OAuth profile in the OS keyring-backed Wrangler store. The default Cloudflare profile remains personal; the `ayahos-hq` profile must enumerate the *actual owning HQ account*. No implicit account switching is allowed.
3. **Nonhuman automation:** Prefer provider-managed short-lived/OIDC or restricted service identities. Octopus gets the required scoped identity; GitHub status is signed by the existing approved bridge, not a newly invented CI path. Secrets belong only in the platform's managed secret store. Never put a broad admin token in an LLM prompt, terminal history, public repository, or CI logs.
4. **Separate authority:** A Cloudflare login grants neither production deployment permission nor deterministic Undermind/Action Gateway authority. Inspect access and release acceptance independently.
5. **Least privilege and recovery:** Read-only diagnostics first; explicit approval for mutations. Scope by project/account, audit access, rotate credentials where exposed, and revoke stale principals. Do not extend token lifetime merely to suppress MFA.

## Repeatable local diagnostic (no secrets printed)

Requires Python 3.11+, GitHub CLI, Wrangler 4 with named profile support, and Octopus CLI.

```sh
python3 scripts/hq/access_doctor.py --cloudflare-account-id YOUR_VERIFIED_32_HEX_HQ_ACCOUNT_ID --json
python3 -m unittest discover -s scripts -p 'test_access_doctor.py' -v
```

The account ID is an **identifier**, not an API token. Pass it through a local
operator command only; do not commit it to this public repository. The doctor
uses exact read-only CLI commands, does not read credential files, suppresses
raw CLI output, and fails closed for an unknown or wrong Cloudflare account.
`ready_read_only` for Octopus proves *space-list access only*, never deploy authority.

### One-time, owner-approved bootstrap

- **GitHub:** `gh auth status` and `gh api user --jq .login`. If the wrong identity is active, use `gh auth switch` / `gh auth login` interactively. Do not create a new broad PAT.
- **Cloudflare:** The HQ account owner opens the **specific** `ayahos-hq-verification-bridge` Worker and selects **Invite**. Start with **Metadata Read-Only** (settings, logs, traces) scoped to this Worker, promoting to Content Read-Only only if necessary to debug the build; use Editor only for a separately approved deployment. Cloudflare supports individual-Worker roles, so account-wide administrator access is unnecessary. After membership is accepted, run `wrangler auth create ayahos-hq` **on the authorized desktop**. Complete the browser's localhost OAuth callback there. Verify `wrangler whoami --profile ayahos-hq` includes the target account, and separately verify the specific Worker is readable. Keep the personal default profile untouched. If an old exposed token exists, revoke/rotate it; never reuse a token pasted into chat.
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
- https://developers.cloudflare.com/workers/ci-cd/builds/configuration/
- https://developers.cloudflare.com/workers/ci-cd/builds/troubleshoot/
- https://octopus.com/docs/octopus-rest-api/cli/octopus-login
