# P3 — Constrained quantitative routing (offline / advisory)

The new `dual_lineage.route_optimization.optimize_route()` produces an
operator-reviewable **recommendation**, never an executable route. The route
candidate set is taken directly from an existing `RoutingPolicy.decide()`
result, which has already excluded disallowed local/cloud routes. Any
excluded route present in evidence invalidates the comparison. P3 adds
fail-closed checks for unverified context capacity and heavy-compute approval.

## Objective

For each route `r` observed on the *same* cases and workload profile:

```
J(r) = mean_cost_usd(r)
     + latency_cost_per_second * mean_latency_ms(r) / 1000
     + failure_penalty_usd * [1 - Beta_2.5%_quantile(1+successes, 1+failures)]
```

Subject to:

- At least 100 matched trials per route by default.
- Identical case-id population and exact workload profile for every candidate.
- Positive, finite, actual-cost and timing measurements.
- The lower 95% posterior credible bound on completion ≥ 0.90 (configurable).
- An optional maximum mean-latency constraint.
- Every candidate is already permitted by the existing deterministic policy,
  has a known context capacity, and meets any heavy-approval constraint.

If these conditions cannot be established, `HOLD` is returned, not a guess.
A minimizer is chosen only among qualified candidates; objective tradeoffs
never override risk thresholds or route authorization. Re-running with
identical evidence is deterministic.

## Boundaries and caveats

The `benchmark_git_sha` marks the commit associated with the experiment,
but is not cryptographic proof the observations happened. Authenticating
case-level evidence, its operator attestation, and case-family stratification
remain prerequisites for deployment decisions. Matched cases reduce demand
mix confounding, but do not alone remove execution-order or environmental
bias. This phase never trains a model.

**Overmind:** Can consume the advisory recommendation when future operator
surfaces are built.

**Undermind:** Retains sole deterministic authority over permissions,
actuators, confirmation, secrets, node/cloud approval, and interrupts.

**Shared Spine:** Existing structured decisions and outcomes remain the
source of operational traces. P3 operates over frozen, independently collected
case-level evidence without reading prompt text or persisting user content.

**Deployment placement:** Only Python stdlib and existing P2 beta quantile
helper are used. The optimizer is small enough for Render, with large trial
execution kept on Node 1 or cloud compute. No live route-selection changes,
fallback modifications, or performance/safety claims are made.
