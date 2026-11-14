# Runtime Observability

AyahOS Dual-Lineage exposes structured operational telemetry without treating hidden reasoning or raw
request content as observability data.

## Surfaces

### Admin console

The internal `/control` console combines authenticated runtime health, incident retention,
provider-performance summaries, release evidence, recent bounded response feedback, and
operational-learning readiness. It labels memory-only and incomplete-coverage states explicitly.
Feedback rows use keyed pseudonymous request identifiers and contain no prompt or response text.
The console is a review surface: critic output remains advisory, deterministic Undermind remains
authoritative, and no automatic training or model promotion is initiated from the page.

### Shared Spine

The Shared Spine remains the authoritative per-request event history. It records typed decisions,
routing, cumulative runtime usage, interrupts, action outcomes, shadow predictions, critic assessments,
and terminal outcome codes.

### Datadog

When `DD_API_KEY` is configured, the API sends bounded-cardinality metrics and sanitized exception
events directly to Datadog. Request IDs, prompts, responses, and generated text are not included in
Datadog payloads.

Terminal cognition metrics include:

- `goblin.dual_lineage.cognition.requests`
- `goblin.dual_lineage.cognition.latency_ms`
- `goblin.dual_lineage.cognition.tokens`
- `goblin.dual_lineage.cognition.output_tokens`
- `goblin.dual_lineage.cognition.cost_usd`
- `goblin.dual_lineage.cognition.runtime_ms`
- `goblin.dual_lineage.cognition.interrupts`
- `goblin.dual_lineage.cognition.incidents`
- `goblin.dual_lineage.transport.sse.keepalives`
- `goblin.dual_lineage.transport.sse.disconnects`

Existing shadow, evidence, and local-dispatch metrics remain available.

The versioned [AyahOS dashboard and Octopus setup lane](../../deploy/datadog/README.md)
provide offline validation, read-only planning, marked-dashboard create/update, and a
live metric-delivery check. Dashboard publishing requires `DD_API_KEY` plus a scoped
`DD_APP_KEY` in the operator deployment context; the API exporter only needs `DD_API_KEY`.
No Datadog credentials are added to PR verification. The `/control` configured flag
reports credential presence only; successful delivery must be checked separately.

`GET /v1/runtime/health` additionally reports `datadog_delivery` (`disabled`,
`unverified`, `accepted`, or `failing`), accepted/failed intake-request counts, the
last acceptance time, and the latest HTTP status or exception type. These counters
cover metric and event HTTP requests in the responding API process and reset on
restart. The latest completed attempt determines delivery state; a later accepted
request clears the error state without discarding the accumulated failure count.
The console displays this information separately from key presence. No key values,
payloads, exception messages, or provider endpoints enter the health response.
HTTP intake acceptance does not establish that Datadog indexed the metrics; use
the read-only `check` command and inspect actual feedback review records for that
end-to-end evidence. Exporter failures remain non-authoritative and do not change
deterministic policy, routing, or cognition decisions.

## Provider comparison baseline

Each provider-backed request records a content-free observation containing provider/model/route,
time to first token, total latency, timeout flag, HTTP status, classified error type, empty-response
flag, incomplete-stream flag, tokens per second, and cost. Datadog receives the corresponding
provider-tagged metrics, and `/v1/runtime/provider-metrics` exposes bounded retained observations
to an authenticated operator.

Routing decisions must not change from these observations until at least 24 hours of comparable
provider data has been retained for the same request population. The repository implements and records
the baseline. Verify the retained evidence directly with:

```bash
ruby scripts/provider_metrics_gate.py
```

For the deployed API, the live gate runs in the Ruby worker. Set `PROVIDER_METRICS_URL`
to the API root and provide the key in `LIVE_RUNTIME_API_KEY` (or name another variable
with `--api-key-env=NAME`):

```bash
export PROVIDER_METRICS_URL=https://<api-host>
export LIVE_RUNTIME_API_KEY=<key>
ruby apps/ruby_worker/bin/goblin-workflow provider-metrics-gate
```

It exits 0 when the window is comparable, 1 when it is not (routing must remain unchanged),
and 2 when the check could not run. The live gate reads `/v1/runtime/provider-metrics` with
`X-Dual-Lineage-Key` through the generated contract client; it does not print or persist the
key, and it reports the API's own `comparable_24h` verdict rather than recomputing it. The
worker scheduler also enqueues an hourly `provider_metrics_gate` job that records the same
verdict. The Render blueprint sets a 168-hour retention
window and 50,000-entry bound, while PostgreSQL provides the durable store.
Phase timings use the same PostgreSQL mode and retention window through migration
010, with JSONL as the local fallback.

After warm traffic exists, the performance exit gate checks the warm provider p95,
the three required phase timings, and the runtime ceiling:

```bash
ruby scripts/performance_gate.rb --url "$PROVIDER_METRICS_URL"
```

The gate is read-only and exits nonzero until each of at least two providers has observations spanning
24 hours. A 24-hour live evidence window is not established by local tests.

The public site defaults to a 28-second request deadline, caps it at 30 seconds, and
uses the streaming cognition route when the client requests SSE. This leaves margin
below the hosting platform's 120-second request ceiling; the live performance gate
still must verify actual warm traffic after deployment.

The canonical Render blueprint currently has no persistent disk for the API service. Do not treat a
JSONL path on that ephemeral filesystem as durable 24-hour evidence. When PostgreSQL mode is enabled,
the recorder uses the `dual_lineage_provider_metrics` table created by migration 008; otherwise,
configure persistent storage or retain the provider-tagged Datadog metrics before starting the
baseline window.

The authenticated endpoint also returns per-provider summaries with timeout, empty-response, and
incomplete-stream rates; mean latency, TTFT, throughput, and cost; status/error counts; and observed
models/routes. It also labels the first request for each provider as cold and exposes warm-request
counts and p95 latency separately. Datadog phase timings are emitted as
`performance.retrieval_wait_ms`, `performance.provider_wait_ms`,
`performance.model_generation_wait_ms`, and `performance.local_compute_wait_ms`.

## Exact usage versus enforcement usage

Streaming keeps two deliberately separate accounting views:

1. **Runtime monotonic usage** is conservative and never decreases. It exists to enforce the immutable
   token, cost, and runtime envelope while generation is active.
2. **Provider-exact usage** is preserved separately when a provider reports authoritative token usage
   and cost.

A conservative estimate may be higher than the provider's final completion-token count. The system does
not rewrite the Shared Spine backwards merely to make the numbers look tidy. Exported terminal billing
telemetry prefers the provider-exact report when one exists, while enforcement keeps its monotonic value.

The SSE contract exposes both views through `usage`, `usage_is_estimated`, `provider_usage`, and
`provider_cost_usd`.

## SSE transport

The cognition stream emits comment heartbeats while the upstream model is quiet. The default heartbeat
interval is 15 seconds and is configurable with `DUAL_LINEAGE_SSE_HEARTBEAT_SECONDS`.

If the HTTP client disconnects, the transport requests cancellation through the existing interrupt
controller and closes the upstream async iterator. Disconnects and emitted heartbeats are counted as
transport telemetry.

## Dependency health

`GET /v1/runtime/health` is protected by the runtime API key and reports:

- configured provider health, role, locality, and probe latency;
- operational-learning store health when enabled;
- whether Datadog export is configured;
- incident-retention status;
- the current build SHA when available.

Provider probes use `DUAL_LINEAGE_HEALTH_PROBE_TIMEOUT_SECONDS` and return only structured status and
error type. Provider credentials, endpoints, request bodies, and exception strings are not returned.

The same health state is proxied to the internal operator web surface and rendered under `/control`.

## Incident snapshots

Abnormal terminal outcomes are retained as bounded, content-free diagnostic snapshots. A snapshot may
contain:

- a keyed pseudonymous request hash;
- terminal status and outcome code;
- provider/model/node identifiers;
- deterministic decision and interrupt reason;
- token/cost/runtime totals;
- whether usage came from an exact provider report or the monotonic runtime meter;
- exception type.

It never contains the raw request ID, prompt, response, generated text, credentials, or exception
message.

The in-process ring size is controlled by `DUAL_LINEAGE_INCIDENT_BUFFER_SIZE`. In PostgreSQL mode,
incidents are loaded from and appended to `dual_lineage_incident_snapshots` using `DATABASE_URL`
(or `DUAL_LINEAGE_INCIDENT_DATABASE_URL`) and retained for
`DUAL_LINEAGE_INCIDENT_RETENTION_DAYS` before purge. Local mode may use the bounded JSONL
fallback at `DUAL_LINEAGE_INCIDENT_LOG_PATH`; Render does not configure that ephemeral fallback.

`DUAL_LINEAGE_TELEMETRY_HASH_KEY` may provide a stable HMAC key for pseudonymous request identifiers.
When it is absent, the runtime API key is reused if configured. Otherwise a process-local random key is
used, so identifiers do not remain correlatable across restarts.

`GET /v1/runtime/incidents` returns the retained redacted snapshots and retention status to an
authenticated operator.

`POST /v1/cognition/{request_id}/feedback` accepts one bounded human rating after a terminal
request, records it on the Shared Spine, and emits a `feedback.responses` telemetry counter.
`GET /v1/runtime/feedback` returns the bounded cross-request feedback index used by `/control`.
It requires the runtime key and returns only a keyed request identifier, terminal status, rating,
reason, source, and optional critic/policy comparison metadata.

## Privacy and failure behavior

Observability is non-authoritative. Datadog delivery failures and incident-store write failures do not
change the deterministic cognition decision. Persistence failures mark runtime health degraded and emit
a `Dual-lineage incident persistence failure` error event so storage loss is visible. PostgreSQL writes
and retention purges share one transaction per incident, so a partial write is rolled back.

Generated text is still returned to the client but is not copied into telemetry or incident snapshots.

## Routing rollout evidence

`GET /v1/runtime/routing` combines observe-mode decision agreement, failover counts and authenticated-probe results with
the retained provider metrics above. Interpretation and stage gates are in [`routing-rollout.md`](routing-rollout.md).
