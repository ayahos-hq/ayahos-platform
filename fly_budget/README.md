# AyahOS Fly.io $5/month budget admission guard

**Scope:** Entire Fly billing organization. **Ceiling:** 500 US cents/month.
**Status:** Source-only, not integrated into the existing Octopus production release. This is NOT an actual Fly.io account-level hard cap.

The package provides budget estimation, strict config policy, authenticated live inventory checks via Fly CLI and an optional guarded deploy entrypoint. It refuses to deploy without current operator-attested billing evidence, a matching organization, and at most one small Machine.

## Admission controls

- Billing statement must be operator-verified from the authenticated Fly billing dashboard, for the current calendar month, no more than six hours old.
- Includes billed + pending + other projected charges, full 31-day upper-bound compute, and **$0.75** of additional overhead reserve.
- Only one existing Fly app may be in the organization. No more than one Machine per app, and no extra apps. Additional existing services require financial reconciliation before the package can be used.
- Allowed region: Ashburn (iad) or Secaucus (ewr). Only 1 shared CPU and 256/512 MB memory, one HTTP service, no volumes, no extra workers or databases, no paid advanced features.
- Required: auto-stop=stop, auto-start=true, min-machines-running=0, HTTPS, and Compact Cognition shadow only.
- Guarded Fly deployment explicitly passes --ha=false to avoid automatically provisioning an HA spare. It rechecks live inventory after deployment and fails if duplicate resources appear.
- Missing Fly CLI, authorization, verified billing, valid service inventory, or budget headroom results in DENY, never a guessed allowance.

**Fly is pay-as-you-go; there is no guaranteed $5 hard cap.** Stopped-Machine rootfs, egress, reserved IPs, extensions, delayed usage reporting and actions outside this entrypoint can exceed the budget. The guard can block *its own* deployments but cannot unilaterally suspend Fly account billing.

Fly official pricing: https://fly.io/docs/about/pricing/

## Worst-case 31-day estimate in lowest-cost supported regions

| Profile | Started 31 days | +$0.75 overhead reserve | Headroom under $5 at zero preexisting spend |
| --- | ---: | ---: | ---: |
| One shared-cpu-1x 256 MB | $2.27 | $3.02 | $1.98 |
| One shared-cpu-1x 512 MB | $3.82 | $4.57 | $0.43 |
| Two 256 MB Machines | About $4.53 | About $5.28 | Denied |

Prices vary by region and billable components; these are indicative 31-day upper-bound compute estimates, not real account charges.

## Billing snapshot

Fill a PRIVATE JSON file using real authenticated Fly organization billing, not the included example (which is deliberately invalid). Required fields:

- organization: exact Fly billing organization slug
- source: authenticated_fly_billing_dashboard
- observed_at: recent ISO 8601 UTC timestamp, within six hours
- month: YYYY-MM calendar billing month
- spent_cents: verified billed-to-date
- pending_cents: reserved/unbilled known usage
- other_resources_projected_cents: all OTHER expected organization-level costs not in the single proposed Machine
- existing_billing_apps_count: 0 or 1 from the authenticated app inventory
- attested_by_operator: true only after checking live Fly dashboard

No account billing, organization slug, app name, token, or credential has been inferred from past chat messages. The private billing file and authentication must not be committed to Git.

## Gate + deployment

Run unit tests:
```sh
python3 -m unittest discover -s fly_budget -p 'test_*.py' -v
```

With an authenticated Fly CLI, a verified existing target app, a reviewed real fly.toml and a current private billing snapshot, request a no-write assessment:

```sh
python3 fly_budget/guarded_deploy.py --fly-config /secure/staging/fly.toml --billing-snapshot /secure/billing/actual.json --organization YOUR_REAL_ORG
```

A successful preflight is NOT a deployment. Only after the release has passed the existing Octopus gate and an explicitly approved release source has been assembled may the operator add --execute and an existing immutable OCI image digest, supplied as --image-digest registry.fly.io/APP@sha256:64HEX. The wrapper then invokes Fly with --ha=false and --update-only (no implicit Machine creation), uses exactly that pinned image and rechecks Machine inventory. It will never create an app, build from unpinned working-tree source, or change secrets.

If the Fly CLI is missing or unauthenticated, the command denies the operation. Post-release authenticated HTTP, policy parity and rollback verification remain mandatory. Do not call this guard a provider-enforced billing limit, continuous monitoring, or a replacement for Octopus.

## Current verified environment blockers

At code creation (October 26, 2026), the inspected connected Windows desktop did not expose an installed authenticated flyctl, and the five provisional HQ repositories did not identify confirmed Fly app names or deployment targets. The original Render control plane is suspended for exceeding its free-tier allowance; it is NOT the target for new AyahOS releases. The local Compact Cognition instance remains separate from the cloud deployment.

**Decision for Fly activation until credentials, app identity, current billing and Octopus release authority are proven: DENY spending and DENY cloud deploy.** Keep testing on Node 001 staging meanwhile.

## Read-only Fly credential preflight (staging)

The HQ Octopus project now holds an independently managed **Sensitive**, Staging-scoped
variable named `Fly_API_TOKEN`. It does not automatically provision `flyctl`,
create a Fly application, or authorize a deployment.

`fly_budget/credential_probe.py` is a deliberately separate diagnostic. On an
approved Staging worker, the operator should securely map the sensitive Octopus
variable into the child process environment as `FLY_API_TOKEN` using the native
Octopus protected-variable mechanism. Never place the value in Git, command
arguments, build logs, an unprotected Octopus variable, or a terminal transcript.
The Python utility executes only `flyctl auth whoami`, discards provider output,
and prints one generic `PASS` or `DENY` line. Failures are nonzero and do
not disclose the credential or API error bodies.

Run the focused offline test suite without provider credentials:

```sh
python3 -m unittest discover -s fly_budget -p 'test_*.py' -v
```

Passing this identity check does **not** establish Fly organization ownership,
budget safety, preexisting app availability, deployed runtime health or
Octopus approval. Continue to require fresh billing/inventory evidence,
immutable image digests, full Octopus gates and authenticated E2E checks.
No new Fly app may be created by this source-only change.

## Live organization reconciliation checkpoint, 2026-10-27

The authenticated CLI currently identifies `ayahos.dev@gmail.com` in organization
`ayahos` (not the earlier inferred personal-org slug). Fly CLI emits app
`Organization` as an object with `Slug`; the guard now checks this schema
and recognizes the reviewed standalone Core `Dockerfile.fly` and its exact
`/health` check without allowing arbitrary build paths or health endpoints.

Fly inventory showed:
- `ayahos-control-api`: app exists, no Machines or secrets reported.
- `ayahos-admin`: suspended with one stopped 1 GB shared-CPU Machine.
- `fly-builder-kind-voice-8348`: stopped 8-vCPU, 8 GB **remote builder**
  with a 50 GB `machine_data` volume mounted at `/data`. This is Fly's
  replaceable BuildKit cache, not app or database storage.

The unused builder was removed after verifying its Fly `rchab` image and
remote-cache mount. Fly CLI acknowledged deletion; this avoids ongoing
provisioned storage at $0.15/GB/month ($7.50/month at 50 GB). Remote Fly builds
can recreate billable builder cache; prefer reviewed local builds or immutable
pre-built OCI images. No Admin or Control API Machine was started or deleted.

The authenticated Fly Cost Explorer displayed $0.00 spend October 21-27,
but billing can lag and there is **no Fly-enforced $5 hard ceiling**.
The guard **still denies multiple apps** until an independently reconciled
inventory includes stopped Admin rootfs, IPs, snapshot charges and all other
unbilled resources. Do not invent a zero pending balance.

Octopus HQ Verification Development release `0.0.19`, task
`ServerTasks-3764`, passed all THREE configured source/offline steps
against Platform `3625777` and Core `5f0e986`. This is NOT the missing
five-repository/eight-lane production release gate. The protected
`octopus/hq-operator-verified` status must remain absent until complete.
