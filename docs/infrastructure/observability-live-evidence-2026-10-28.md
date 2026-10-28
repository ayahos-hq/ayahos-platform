# AyahOS HQ observability — verified Fly and Datadog checkpoint

Evidence date: 2026-10-28 UTC. This record documents observed state; it is NOT an authorized release or production cutover.

## Read-only observations

- Fly app ayahos-control-api has one started machine in iad, and one HTTP health check passing. The health body reports status ok and service goblinos-dual-lineage-api. This does not prove inference, streaming, or evidence persistence.
- Fly app ayahos-admin has a stopped machine and no active check demonstrated. Its configured auto-stop policy means stopped is not proof of application failure.
- The control API Fly secret inventory confirms DD_API_KEY, DD_ENV, DD_SERVICE and DD_SITE are deployed; only names/status were inspected, not secret values.
- The Admin secret inventory shows the Supabase operator-auth settings and deployment role. It does not list GOBLIN_API_BASE_URL, GOBLIN_API_KEY, or GOBLIN_OPERATOR_SECRET. These could be set via another configuration mechanism; verify effective settings safely before claiming the protected Admin proxy works.
- AyahOS Datadog dashboard qkr-8e7-6jg exists. Production-tagged cognition-request and feedback metrics have historical data from October 22, but no indexed data in the past 24 hours. The corresponding unfiltered metrics also showed no data in that 24-hour interval. Missing metrics are not evidence of zero traffic or backend failure.

Dashboard: https://app.datadoghq.com/dashboard/qkr-8e7-6jg/ayahos--runtime-and-feedback-loop

## Verification sequence

1. Identify the currently deployed Fly image digest and source SHA from authoritative release metadata; do not infer it from a GitHub branch or a successful health probe.
2. Read only non-sensitive DD_ENV, DD_SERVICE and DD_SITE settings, current intake acceptance/failure counters, and process restart history. Never print DD_API_KEY or HTTP payloads.
3. Run one owner-authorized bounded synthetic cognition request and an opt-in feedback test through the current deployment. Capture redacted Core terminal status, hashed evidence key and sampled latency. Withdraw any test learning evidence when appropriate.
4. Query Datadog with actual runtime tags, then without filters, for the precise test interval. Require an indexed metric; intake HTTP acceptance alone is insufficient.
5. In protected Admin staging, test enrolled Supabase sign-in sessions, unauthorized/expired/replayed sessions, signout, same-origin checks and trace/incident redaction.
6. Verify Admin-to-Core machine credentials and base URL only through server-side probes; keep privileged runtime mutations disabled until operator policy tests pass.
7. Prove incident/release evidence survives a process restart and remains explicitly non-durable on database failure. Exercise cross-machine incident reads against isolated PostgreSQL 16/pgvector.
8. Require exact-SHA/OCI digest assembly, cross-repository contract gates, Octopus acceptance, isolated restore, live chat/SSE and rollback before service-by-service production cutover.

## Gated acceptance

| Gate | Current evidence |
| --- | --- |
| Fly control health | Passing 1/1, 2026-10-28 |
| Fly Admin operator sessions | Not proved |
| Protected Admin Core proxy | Not proved |
| Datadog indexed request/feedback from current Fly | Not proved, prior 24h no data |
| Durable evidence/incident history | Source fixes staged in Core PR #49; live pending |
| Admin telemetry contract | Staged in Admin PR #19; protected hosting pending |
| Octopus exact-SHA and recovery/rollback | Pending release-manifest attestations |

## Architecture ownership

Core owns observability contracts, single Undermind authority and Shared Spine. Admin owns read-only operator diagnosis; privileged controls remain independently protected. Platform owns deployment provenance and continuity verification. Site and Workloads contribute redacted, correlated telemetry, never a second governance path.

Keep the existing production source authority until each service has a verified cutover. The remaining work includes safe telemetry export buffering, full distributed tracing, alerts, FinOps attribution and incident triage UX. Do not claim these complete from this checkpoint. Avoid paid monitoring agents or new persistent infrastructure without a budget assessment.
