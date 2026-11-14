# P5 — Operational route canary and emergency rollback

**Status:** Canary code and offline operator gate are implemented in a feature
branch, not released or enabled. A GitHub merge and green CI do not by themselves
authorize this rollout.

## What changes at request time

`RolloutConfig` now supports a *separate* stable routing canary bucket.
It does not alter the existing provider-failure fallback percentage.

| Variable | Default | Meaning |
| --- | --- | --- |
| `DUAL_LINEAGE_ROUTING_MODE` | `observe` | Existing policy: `observe` continues to run the configured priority |
| `DUAL_LINEAGE_ROUTE_CANARY_PERCENT` | `100` | Share of requests selected by the policy **only if** mode is explicitly `enforce` |
| `DUAL_LINEAGE_ROUTE_EMERGENCY_OBSERVE` | `false` | Overrides `enforce` and serves configured priority even for canary requests |
| `DUAL_LINEAGE_FALLBACK_PERCENT` | `100` | Separate existing provider failure fallback cohort |

These defaults preserve prior explicit `enforce` behavior and default observe
behavior. To test 5%, an operator must explicitly set `enforce` and `5`
in reviewed runtime config after passing preflight tests and live proof.

Canary allocation is deterministic for each request ID, independent from
fallback allocation. The actual route mode and an integer canary bucket are
added to content-free `compute_selected` Shared Spine labels. Manually
pinned routes bypass policy allocation and should be excluded from analysis.

**Emergency action:** Reconfigure
`DUAL_LINEAGE_ROUTE_EMERGENCY_OBSERVE=true`; redeploy/restart all API replicas
and verify `GET /v1/runtime/routing` reports the flag and serving mode. This
reverts route selection to legacy priority, **not** all provider failover.
Set `DUAL_LINEAGE_FALLBACK_PERCENT=0` separately if cross-provider fallback
must also stop. Configuration changes are *not instant*, and do not
cancel already executing requests. If runtime health is compromised,
redeploy the known previous SHA.

## Operational evidence: separate from synthetic benchmarks

P4 offline held-out gate passing is a precondition, never production proof.
For P5, correlate real `compute_selected` Spine events with *terminal*
request events by actual request ID in a trusted, access-controlled exporter.
Export only opaque unique request tokens, canary bucket, profile, selected
route identifier, timestamp, commit, policy version, completion state, total
latency, actual request cost, and validated critical permission-violation flag.

No prompts, user identifiers, output text, authentication secrets or
raw request IDs belong in the evidence artifact.

The analytical gate accepts such normalized observations from a trusted
collector; it does **not** itself attest a supplied artifact, operate a
Spine exporter, or change routing. The caller must verify event joins,
authenticity, storage, and deployment SHA. The integer cohort bucket alone
cannot establish which provider was permitted; inspect the underlying
Undermind and route decision for permission violations.

The read-only `evaluate_operational_canary()` requires:
- A consistent deployment SHA and policy version on all samples.
- Durable provenance-verified request-level operational evidence.
- Valid bucket assignment and unique request tokens.
- At least 250 baseline and 250 canary requests per represented workload
  profile, each spanning at least 24 hours with fresh measurements.
- No reported permission-boundary violations.
- No statistically supported completion regression or unsafe p95
  latency / request-cost increase.

The gate's three possible results:
- **ROLLBACK**: urgent **manual** revert recommendation after a verified
  permission violation, significant failure-rate increase, or severe
  latency/cost regression.
- **HOLD**: inadequate, stale, ambiguous, or inconclusive evidence.
- **REVIEW_ADVANCE**: *operator may review* moving from 1 -> 5 -> 20 ->
  50 -> 100 percent. The code never advances cohorts itself.

**Important gaps before production use:** This first P5 increment does not
yet include a durable automatic per-replica kill switch, independently
attested counterfactual demand matching, or live collection from Spine into
the normalized gate data. The gate must never be described as an automatic
cross-replica rollback mechanism. Existing `/v1/runtime/routing` provides
in-process counters and retained provider metrics, not this complete
cohort-level outcome history. Integrating a durable collector and global
rollback actuator should be a separate reviewed change.

## Overmind / Undermind / Shared Spine

- **Overmind:** ranking only for the permitted canary cohort. Advisory
  statistical evidence never authorizes an actuator.
- **Undermind:** deterministic preflight, budgets, confirmation, local/cloud
  scope and Action Gateway remain the hard authority boundary.
- **Shared Spine:** immutable request-level route/terminal traces are the
  source from which a trusted operator collector must derive P5 data.

This is lightweight Python stdlib, deployable on the API runtime. Any
large-scale replay or model fitting belongs on Node 1 or external compute.

## Offline operator CLI

Normalize authenticated, retained Shared Spine route-selection and terminal
events into a **content-free** JSON artifact containing
`source="shared_spine_join"`, `deployment_sha`, `canary_percent`,
`persisted`, `provenance_verified`, `outcomes`, and
`evidence_sha256`. Each outcome includes only the strict
`OperationalRouteOutcome` fields. The SHA-256 digest is computed on the
canonical JSON object without `evidence_sha256`, sorted keys and compact
separators. **A self-computed digest is integrity checking, not a trusted
attestation of origin.** Verify source records independently.

```bash
python scripts/operational_route_gate.py --evidence path/to/verified-outcomes.json --expected-deployment-sha <40-character-git-sha> --expected-canary-percent 5
```

Exit codes: 0 = `REVIEW_ADVANCE`, 1 = `HOLD`, 2 = malformed artifact
(`INVALID`), 3 = urgent `ROLLBACK` recommendation. Never treat 0 as
permission for automated rollout; a separate operator review is mandatory.
