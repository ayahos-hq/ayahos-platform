# P4 — Held-out shadow routing review gate

P4 is an **offline**, content-free replay evaluator for a proposed change to
the route selector. It compares *two recorded outcomes on each case*: the
configured baseline and a proposed shadow policy. It does not call providers,
alter the live routing decision, change fallback ordering or permissions, or
promote a classifier.

For each reviewed workload profile, minimum 500 unique held-out case IDs
(default) are required. Each case contains both routes, the
`allowed_route_keys (an artifact-declared claim that must be externally checked against the actual RoutingPolicy decision)` authorized by the already-deterministic policy,
completion results, observed latency/cost and critical-failure flags. Mixed
profiles and cases seen during training/tuning cannot be treated as holdout.

The core gates use 2,000 seeded paired percentile bootstrap resamples:

- **Completion noninferiority**: lower 95% bootstrap bound on
  (shadow minus baseline completion) >= -0.01; additionally, a
  conservative Wilson upper 95% confidence bound on incumbent-only
  successes must be <= 0.01. This avoids falsely precise zero-width
  bootstrap intervals when no paired outcomes disagree.
- **Cost**: upper 95% bound on cost regression <= $0/case.
- **Latency**: upper 95% bound on latency regression <= 100 ms/case.
- **Required improvement**: upper 95% bound on cost difference <=
  -$0.0001/case *or* latency difference <= -50 ms.
- Zero observed shadow critical failures. That observation does not establish
  zero real-world incident probability.

All statistics are matched by case. Bad/future/stale timestamps (default
30-day lookback), missing or duplicate IDs, unknown route permission context,
missing/duplicate training-case references, training/holdout overlaps,
malformed or identical commit hashes, synthetic
replays and unknown measurements return **HOLD**. The benchmark source
label and Git SHAs are not independent proof of data authenticity; external
attestation and a real holdout collection process remain necessary.

The result is `REVIEW`, not `PROMOTE`, when numerical gates pass. A
human operator must verify original case provenance, model/route configs,
critical event definitions, demand distribution, risk thresholds and CI
results before choosing a separate controlled rollout.

**Architecture:** Undermind's deterministic authorization, Action Gateway,
budgets, confirmation, local/cloud permissions and fail-closed behavior are
unchanged. Overmind may inspect the review, never use it as authority.
Shared Spine retains the real request-event evidence separately. This module
only consumes frozen, content-free outcome pairs.

**Placement:** Python standard library plus existing bench statistics and
route contracts on Render; run large replay and model work on Node 1/cloud.

**Verification:** Focused regression tests belong to the `routing_failover`
release gate; do not promote without full CI, live telemetry and human review.


## Read-only artifact CLI

Use a JSON artifact containing exactly `baseline_sha`, `shadow_sha`,
`source_kind`, `training_case_ids`, `pairs`, and `evidence_sha256`.
Each row contains only the numeric/binary observations, timestamp, route
eligibility and non-content case ID represented by `ShadowRoutePair`.
Additional fields (including prompt text) are invalid.

The SHA-256 digest is computed from the canonical JSON of the entire artifact
*without* `evidence_sha256` (sorted keys, compact separators, UTF-8).
This detects accidental modification of the input artifact, **not forgery**;
external provenance or signature validation is still required.

```bash
python scripts/shadow_route_gate.py --report /path/to/heldout.json --expected-baseline-sha <40-hex-commit> --expected-shadow-sha <40-hex-commit>
```

Exit statuses: 0 = `REVIEW` (manual examination justified, no promotion);
1 = `HOLD` (insufficient or regressed evidence);
2 = `INVALID` (malformed or tampered artifact/revision mismatch).
