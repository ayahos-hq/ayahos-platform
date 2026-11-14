# Routing rollout runbook (Phase 6)

How provider routing and cross-provider failover reach production in stages, what to watch at each
stage, when to advance, and how to roll back. Authority does not change at any stage: deterministic
Undermind policy still decides what may run, failover only re-runs the *same* request on another
route the request was already permitted to use, and a pinned provider never fails over.

Status of each stage on a given commit lives in the release handoff for that commit
(for example [`release-handoff-2026-10-05-phase6.md`](../release-handoff-2026-10-05-phase6.md)).
A stage is **not** reached because the code exists; it is reached when its evidence is retained.

## Controls

All are API service environment variables, set in `render.yaml` so a stage change is a reviewed commit.
Unparsable values fall back to the safe default and log a warning.

| Variable | Default | Effect |
| --- | --- | --- |
| `DUAL_LINEAGE_ROUTING_MODE` | `observe` | `observe`: the routing policy ranks routes and records what it *would* pick (Spine label, `routing.decision` metric, agreement counters) while configured priority still routes. `enforce`: the policy picks the primary route. |
| `DUAL_LINEAGE_FALLBACK_PERCENT` | `100` (existing serving behavior) | Share of requests (stable hash of `request_id`, so a cohort never flaps) that may fail over to another permitted route after a provider fault. Raising it only adds requests to the cohort. |
| `DUAL_LINEAGE_FALLBACK_MAX_ATTEMPTS` | `1` | Extra routes a cohort request may try (0 to 3), inside the request's one runtime deadline. |
| `DUAL_LINEAGE_DISABLED_PROVIDERS` | empty | Route ids or vendor stems (`aliyun`) removed when the registry is built. Removal only; it cannot add or widen anything. |
| `DUAL_LINEAGE_HEAVY_STRICT_APPROVAL` | `false` | Heavy requests never use a cloud route outside `DUAL_LINEAGE_HEAVY_CLOUD_PROVIDERS`. |

Notes that matter when reading results:

- Same-provider retries (one retry on overload/connection errors) and circuit breakers belong to the
  provider-resilience layer and are independent of the failover percentage.
- Fallback order follows the routing policy ranking (workload fit, health, cost, context window), filtered by the
  request's local/cloud permissions. It is not registry order.
- Streams fail over only before the first chunk reached the client. After output has started, a failure is a
  terminal error; output is never duplicated or spliced.
- Timeouts and user cancellation are terminal. Request-specific 4xx errors (HTTP 400/404/413/422 without a
  model-name cause) neither fail over nor count against a provider's breaker or route health.
- Heavy requests walk the ranked compute-plane peers (nodes and provider peers alike) when the elected peer is
  unavailable: a node that is offline, errors, or misses its probe window, or a provider peer that is no longer
  configured or permitted. The walk spends the same `DUAL_LINEAGE_FALLBACK_MAX_ATTEMPTS` budget and cohort as
  provider failover, and a provider elected after a dead node gets only what is left of that budget. Each attempt
  is a `compute_selected` Spine event labelled `route_attempt=N`; a dead peer's event names it only in
  `route_attempt_peer` (for example `node:node-001`) with `route_attempt_outcome=peer_unavailable`, so the
  request's recorded node/provider is always the peer that actually ran. Running out of deadline between
  peers ends the request as `runtime_timeout`. A request whose peers are all exhausted fails with `no_execution_route`.

## Stages

Move one stage at a time. Each stage lists the change, the entry gate, what to watch, the exit gate, and the rollback.

### 1. Deploy correctness fixes

- **Change:** deploy the candidate with mode `observe` and fallback `100`, preserving the current share of requests eligible for cross-provider failover. A separate reviewed decision is required before changing the fallback cohort to `0` for a staged ramp.
  Failover across providers is **off** at this stage.
- **Entry:** `ruby scripts/release_gate.py` passes on the candidate SHA against real PostgreSQL with zero skips
  (it includes the `routing_failover` group); lint and type checks pass.
- **Watch:** served SHAs on all three surfaces equal the candidate (Render API via authenticated
  `/v1/runtime/status`, Render web `/api/build`, public site `/api/build`). Set `LIVE_EXPECTED_SITE_SHA` to the commit the
  site is *meant* to serve: on 2026-10-05 the site was observed both on the last commit that touched `apps/site`
  (`7bb3980`, while main was ahead of it) and later on the `main` tip, so do not assume either behaviour.
- **Exit:** `ruby scripts/live_release_smoke.rb` passes with `LIVE_EXPECTED_SHA`/`LIVE_EXPECTED_SITE_SHA` set,
  including `timeout_terminal`, `cancellation_endpoint`, `streaming`, `provider_failure` and the three served-SHA
  checks; `scripts/public_chat_smoke.rb` passes.
- **Rollback:** redeploy the previous SHA.

### 2. Metrics-only routing decisions

- **Change:** none beyond stage 1. `observe` is already recording decisions.
- **Entry:** stage 1 exit.
- **Watch** (`GET /v1/runtime/routing`, runtime key): `decisions.agreement_rate` overall and per profile,
  `decisions.top_disagreements` (which route the policy would have preferred), `decisions.errors` (must stay 0:
  a policy exception falls back to configured priority and is counted), and `routing.decision` in Datadog.
  Each request's `compute_selected` Spine event carries `route_mode`, `route_selected` and `route_executed`.
- **Exit:** `LIVE_RUNTIME_API_KEY=<key> ruby apps/ruby_worker/bin/goblin-workflow provider-metrics-gate --url="$API"` reports a comparable 24 hour window
  (at least two providers, each with observations spanning 24 hours), `decisions.errors == 0`, and the disagreement
  list has been reviewed.
- **Rollback:** nothing to roll back; routing is unchanged in this mode.

### 3. Fallback for a small percentage of traffic

- **Change:** `DUAL_LINEAGE_FALLBACK_PERCENT=5`, `DUAL_LINEAGE_FALLBACK_MAX_ATTEMPTS=1`.
- **Entry:** stage 2 exit, and at least two cognitive providers are registered and individually verified.
- **Watch:** `failovers` (`from->to` counts) and `routing.failover` in Datadog; `compute_fallback` Spine events per
  request; the failed-request rate and p95 latency of the cohort versus the rest; **permission invariant:** no
  `compute_fallback` whose target is a local route for a request that did not allow local execution (the tests prove
  this cannot happen; a violation is a stop-the-line incident).
- **Exit:** 24 hours at 5% with no rise in failed-request rate, no latency regression for non-cohort traffic, and
  every observed failover explained by a provider fault in `provider-metrics`.
- **Rollback:** set the percentage back to `0`. Cohorts are nested, so any smaller value is a subset of the current one.

### 4. Compare provider latency, quality, cost and failure rates

Source: `GET /v1/runtime/provider-metrics` (retained, content-free, persisted in PostgreSQL) and `GET /v1/runtime/routing`.

| Dimension | Field |
| --- | --- |
| Latency | `mean_total_latency_ms`, `p95_total_latency_ms`, warm variants `mean_warm_latency_ms`/`p95_warm_latency_ms`, `mean_time_to_first_token_ms` |
| Throughput | `mean_tokens_per_second` |
| Cost | `mean_cost_usd` per request (exact provider usage where reported) |
| Failure | `timeout_rate`, `incomplete_stream_rate`, `error_type_counts`, `http_status_counts` |
| Output floor | `empty_response_rate` |
| **Quality** | **Not measured.** No labelled quality signal is wired in; `empty_response_rate` is only a floor. Use the paired benchmark framework (`docs/research/dual-lineage-bench.md`) or human review before treating one provider as better. |

Compare providers only over the same window, workload mix and cold/warm split. The 24 hour comparability gate exists
for this reason.

### 5. Increase fallback coverage gradually

- **Change:** 5 → 10 → 25 → 50 → 100, one step per reviewed change, each held at least 24 hours.
- **Advance only when** the previous step's exit criteria still hold at the new percentage.
- **Rollback:** the previous value.
- `enforce` mode is **not** part of this rollout. Consider it separately, and only with stage 4 evidence including a
  quality comparison.

### 6. Remove providers that stay unverified or consistently poor

`GET /v1/runtime/routing` returns `recommendations` per registered provider: `keep`, `probation`, `remove` or `hold`.

- `hold` for every provider until the metrics window is comparable. Nothing is recommended for removal on thin evidence.
- **Unverified:** no successful request and no successful authenticated probe (`/v1/runtime/health`) observed.
- **Consistently poor:** at least 3 hourly evaluation windows (each with at least 20 requests) in which the provider-side
  failure rate is 25% or more, or 50% or more of requests are request-specific 4xx errors (a wrong model or a
  broken contract looks like this). One poor window is `probation`, not removal.
- The output is **advisory**. A person decides. To remove a route, add it to `DUAL_LINEAGE_DISABLED_PROVIDERS` (or
  remove its credentials) in a reviewed change and record the evidence that justified it.

## Required release evidence

Retain each item with the exact SHA, UTC time, URL or command, and result in the release handoff. A skipped or
unavailable check is `BLOCKED` or `WARN`, never a pass.

| Evidence | How |
| --- | --- |
| Local provider tests | `pytest` over the provider, resilience and factory test modules (see the handoff for the exact selection and counts) |
| API integration tests | `test_cognition_api.py`, `test_runtime_status_api.py`, `test_routing_api.py`, `test_live_smoke_script.py` |
| Streaming failure tests | `test_streaming_runtime.py`, `test_sse_transport.py`, stream cases in `test_routing_fallback.py` and `test_routing_api.py` |
| Authenticated provider probes | `GET /v1/runtime/health` with the runtime key (provider health), plus `goblin-workflow provider-metrics-gate` |
| Live public-chat smoke | `ruby scripts/public_chat_smoke.rb` (keyless) |
| Timeout / failover smoke | `scripts/live_release_smoke.rb`: `timeout_terminal` (1 ms budget must end terminally with a `timeout` interrupt) and `failover_observed` (passes only on observed failovers) |
| Cancellation smoke | `scripts/live_release_smoke.rb`: `cancellation_endpoint` |
| Served Vercel SHA | public site `/api/build` against `LIVE_EXPECTED_SITE_SHA` |
| Served Render SHA | Render web `/api/build`, and the API's `build_sha` from authenticated `/v1/runtime/status`, against `LIVE_EXPECTED_SHA` |

The smoke script itself is exercised against the real app, with stub site and web servers, in `apps/api/tests/test_live_smoke_script.py`, so
a change to the script is proven before it is used against production.

## Known limits

- Route health (each peer's recent outcomes, which ranking and breaker release read) is shared through PostgreSQL in
  `DUAL_LINEAGE_DATABASE_MODE=postgres` (table `dual_lineage_route_health_outcomes`, migration 022), so a restart or a
  second replica sees the same 300 s window. Each instance refreshes its copy at most every 2 s. If the database
  errors, the instance routes on its own in-memory window and retries the database after 30 s. Local mode keeps
  health in memory only.
- Decision, failover and probe counters are in-process and reset on restart; provider summaries come from the retained
  provider metrics.
- Workload classification is a keyword and length heuristic and is only a routing hint.
- Timeouts are not attributed to providers, because the runtime budget is client-chosen.
- No provider quality signal exists yet.
- None of this is `verified-live` until the handoff for the deployed SHA says so.
