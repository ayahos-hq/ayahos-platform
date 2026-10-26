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
