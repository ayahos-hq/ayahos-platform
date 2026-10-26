# AyahOS Fly.io $5/month spend policy (2026-10-26)

## What is and is not enforced

**The user's ceiling is $5 USD per calendar month for all Fly.io resources.**
Source-controlled AyahOS RELEASE admission now fails closed without an
authenticated, recent, complete organization-wide billing and resource
inventory. The internal admission ceiling is **$4.50** with a $0.50
safety reserve. The default resource envelope permits at most **one**
shared-cpu-1x 256 MB Machine, pinned to Fly region **iad** (North America),
and **zero** additional paid capacity.

**This does NOT guarantee that Fly.io's actual invoice will stay at $5.**
Fly.io support confirmed on 2026-06-15 that it does not offer account-level
hard billing limits. Fly computes charges from actual runtime, stopped
Machine rootfs, persistent volumes, bandwidth, certificates, paid extensions
and other billables. Accrual may precede telemetry; a production runtime
may stay online after a local/pre-deploy guard rejects new releases. Fly.io
has not installed this admission gate on the account.

Primary documentation:
- https://fly.io/docs/about/pricing/
- https://fly.io/pricing-update/
- https://community.fly.io/t/prepaid-budget-used-up-rolled-directly-into-billing/28103

## Implemented package

- `budget/fly-budget-policy.json` — pinned $5 policy, reserve, `iad` region, maximum one
  256 MB Machine, minimum known machine/network tariffs. Larger machines,
  a second Machine, managed DB, volumes, stopped Machines, paid IPv4,
  reservations and unclassified costs are rejected, never silently priced.
- `scripts/fly_budget_guard.py` — independent Python 3 admission gate.
  Rejects unknown schemas, missing org match, old inventory (older than
  15 minutes), stale/different billing cycle, incomplete actual charges,
  unknown resources, forged typed fields or forecast overruns.
- `tests/test_fly_budget_guard.py` — adversarial, calendar-boundary,
  stale-evidence, forged-attestation and budget-exhaustion regression tests.
- `.github/workflows/platform-isolation.yml` — tests this policy on PRs.

**The CLI does not execute a deployment.** Nonzero exit status 3 is DENY;
zero is a source-level admission recommendation, not Fly billing assurance.

## Provider-authenticated collection and release activation (NOT YET DONE)

1. Connect the real Fly.io organization using a freshly scoped credential.
   Do not reuse any token pasted into chat; rotate previously exposed tokens.
   Verify the account slug, billing organization, all apps and Machines,
   deployed digests, invoice preview, existing volumes, networking and
   third-party services. Existing Fly CLI and account token were NOT present
   in the verified connected Windows/Ubuntu environment.
2. Build a collector under independent review that fetches authenticated
   **actual** organization-wide billing data and all resource categories,
   fails closed if incomplete or delayed, and signs the exact normalized
   snapshot. Never represent a manually edited file as verified data.
3. Set `FLY_BUDGET_ATTESTATION_KEY` in a *private* Octopus/secret manager
   environment (min 32-byte secret) and only in the collector/verifier.
   The separate collector signs a canonical JSON document via HMAC SHA-256
   into `attestation_hmac`. Never commit key or live snapshot.
4. Run the CLI as the **mandatory first step** of every authorized
   Octopus → Fly deployment / scale / create / restore workflow. Deny
   for any absent evidence, key, app enumeration or cost category.
   Octopus must be the actual deployed release authority, not a checked-in
   but unattached OCL file.
5. Use continuous **off-platform** spend monitoring, with alerts and a
   signed live Machines API adapter that stops/cordons Machines and blocks
   auto-restarters when forecasts approach the $4.50 reserve. This needs
   verified scoped Fly permissions and should not run from a Machine that
   could itself be stopped. Verify recoverability before stopping services.
   No such authenticated watchdog is currently running.
6. If guaranteed spend cannot exceed $5 is non-negotiable, choose a
   provider that offers a contractual hard limit or avoid running paid
   Fly.io services. Neither prepaid credit nor a payment-card limit is
   a documented contractual guarantee on Fly.io.

### CLI

```sh
FLY_BUDGET_ATTESTATION_KEY='<PRIVATE_SHARED_COLLECTOR_SECRET>' \
python3 scripts/fly_budget_guard.py \
  --policy budget/fly-budget-policy.json \
  --evidence /secure/live-provider-attested-snapshot.json \
  --intent /secure/pinned-release-intent.json
```

The snapshot must include a distinct `attestation_hmac` field, and its
remaining fields must match the v1 schema. A tested sample under
`budget/examples/` intentionally uses `example-only-not-verified` and
always DENIES. Never change the sample to look production-authenticated.

## Cost calculation and safety limits

The gate projects through the end of the **current UTC calendar month**:

```
forecast = actual invoiced-to-date
         + remaining UTC hours × $0.0030 (one smallest Machine)
         + maximum approved remaining egress GB × $0.02
         + maximum approved remaining certificate charges
allow if forecast <= $4.50 AND all evidence/shape checks pass
```

Pricing assumptions must be periodically revalidated against Fly pricing,
including the real Machine region. If the region would be charged more,
the collector must deny rather than substitute this cheaper tariff.
Other costs and taxes can make actual invoices higher. $0.50 is a
planning buffer, not a provider-imposed suspension threshold.

**Observed activation status:** source-level admission policy and tests
are implemented. Actual Fly account cap is unavailable at the platform
level; no remote Fly organization data or machines were modified. The
live billing collector, reconciliation, Octopus attachment and off-platform
shutdown watchdog are still blocked on Fly authentication and an audit of
existing resources. Never describe this repository-only code as a live
$5 invoice hard cap.
