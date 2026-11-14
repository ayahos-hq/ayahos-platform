# P2 — Bayesian provider reliability (advisory)

AyahOS collects content-free provider timing and failure records. P2 adds
a lightweight Beta-Binomial estimate of **completed, non-empty provider
attempts** for the past 24 hours. It is *not* answer quality, policy
compliance, cause of an outage, or a guarantee of future success.

## Model and evidence

Within each `provider_id + model_id + route` stratum:

- Prior: Beta(1,1), a uniform prior chosen for an interpretable baseline.
- Successful attempts: no timeout, incomplete/empty result, provider error,
  HTTP 429, or HTTP 5xx.
- Failures: any of those fault signals.
- HTTP 4xx except 429 are excluded as request/configuration errors unless
  accompanied by timeout, empty response, or incomplete stream.
- Posterior: Beta(1+completed, 1+failed), with posterior mean and **central
  95% credible interval** from the incomplete-beta quantiles.
- A result is `reviewable` only when there are at least 30 observed,
  non-excluded attempts in a recent window **and** evidence is persisted.
  With fewer or non-durable attempts, it reports an explicit insufficiency.
- Event timestamps in the future, timestamps without an offset, and
  observations outside the freshness window are excluded.

The prior, window, and minimum are baseline analytical choices. They require
sensitivity analysis with real demand/failure data. Even `reviewable` means
sufficient basic signal to inspect—not that a provider is safe, production
ready, or better than another provider. Providers may serve different workloads
and only directly comparable requests support a fair ranking.

## Operator usage

```bash
python scripts/provider_reliability.py --path path/to/provider-metrics.jsonl
```

JSON results include sampled counts, excluded request errors, posterior
parameters, uncertainty bounds, and evidence status. The exit status is 0
only if every observed stratum has durable reviewable evidence, 1 for evidence
HOLD, 2 when no path was configured. No API token or prompt text is exported.
The same `ProviderMetricsRecorder.reliability_estimates()` method is available
to the operator-control plane. It does not change the production API or create
a new deployment-time dependency.

**Authority:** Observability and Shared Spine provide outcomes; Overmind
may inspect candidate evidence, but deterministic Undermind rules, local/cloud
permissions, approved compute registry, fallback limits, and the Action Gateway
stay unchanged. No posterior value grants an action or permits a route.
This phase is evidence-only; a separately reviewed future feature may allow
an operator to adjust route selection behind an explicit rollout gate.

**Placement:** Python standard library + existing Pydantic on Render for
bounded reports; use cloud/Node 1 for heavyweight replay, model evaluation,
and offline optimization. Historical provider telemetry remains content-free.
