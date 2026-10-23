# AyahOS Datadog setup

`ayahos-dashboard.json` covers production request counts, sampled latency, incidents,
interrupts, provider errors/timeouts, bounded response feedback by rating, and advisory
learning readiness. It uses the metric names already emitted by the Python API. Its
fixed scope is `env:production,service:goblin-dual-lineage-api`.

## Credentials and deployment

Datadog sign-in through a connector does not populate the API runtime or CI secrets.
The [Datadog API](https://docs.datadoghq.com/api/latest/dashboards/) requires both an
API key and an application key to manage dashboards. Use a dedicated scoped application
key with `dashboards_read`, `dashboards_write`, `metrics_read`, and
`timeseries_query` (needed by the live metric check). Follow the
[key-management guide](https://docs.datadoghq.com/account_management/api-app-keys/).

Store `DD_API_KEY` and `DD_APP_KEY` as sensitive variables in the **operator deployment
context in Octopus**, scoped to the Datadog setup runbook. Keep them out of ordinary
PR verification jobs. The Render API service separately needs `DD_API_KEY` to emit
telemetry; it does not need `DD_APP_KEY`. Its configured tags should be
`DD_ENV=production`, `DD_SERVICE=goblin-dual-lineage-api`, and `DD_SITE=datadoghq.com`.
Secret values must never appear in repository files, chat, artifacts, or logs.

## Repeatable commands

### Local CLI OAuth (no MCP)

Install [Datadog's official Pup CLI](https://github.com/DataDog/pup) and authenticate
with a regular Datadog user that can manage dashboards:

```sh
pup auth login --org AyahOS --scopes dashboards_read,dashboards_write,metrics_read,timeseries_query
pup auth status --org AyahOS
DD_AUTH_METHOD=pup DD_PUP_ORG=AyahOS ruby scripts/datadog_dashboard.rb plan
DD_AUTH_METHOD=pup DD_PUP_ORG=AyahOS ruby scripts/datadog_dashboard.rb apply
DD_AUTH_METHOD=pup DD_PUP_ORG=AyahOS ruby scripts/datadog_dashboard.rb check
```

Set `PUP_BIN` to the executable's absolute path when it is not on PATH. The publisher
passes JSON on stdin and uses the named Pup session. It never runs `pup auth token`,
exports an OAuth token, or prints CLI diagnostic bodies. OAuth approval requires a
normal user; Datadog service accounts authenticate programmatically with keys/tokens.
MCP-specific settings do not control this direct CLI/API path. Runtime metric export
still needs its own API key. Request `api_keys_write` as an additional OAuth scope
only when using the authorized CLI session to provision that runtime key.

### API/application keys (CI or local)

Run from the repository root with Ruby 3.x. No gems are required by the publisher.

```sh
ruby scripts/datadog_dashboard.rb validate  # offline, no credentials
ruby scripts/datadog_dashboard.rb plan      # read-only; reports create/update
ruby scripts/datadog_dashboard.rb apply     # creates or updates only our marked dashboard
ruby scripts/datadog_dashboard.rb check     # read-only; verifies recent request + feedback counts
```

The publisher finds its dashboard using `ayahos-managed:observability-v1` in the
description, refuses ambiguous matches, and never replaces an unmarked dashboard.
Run the first creation once at a time, then pin the returned ID in `DD_DASHBOARD_ID`.
`apply` returns a dashboard ID and a relative URL. Re-running it updates that same
dashboard. To roll back its contents, apply the JSON from an earlier reviewed commit.

For Octopus, use an operator-only runbook script step with Git source at the reviewed
commit, the hosted Ubuntu worker-tools container, and
`scripts/ci/octopus_verify.sh datadog` as the script. Set `DD_DASHBOARD_MODE` to
`plan` (the default), `apply`, or `check`. This lane is not added to required CI or
the automatic release process. Creating the Octopus runbook and supplying sensitive
variables requires an authenticated Octopus connection; committed code alone does
not create that remote runbook. The existing Ruby worker CI lane runs offline
publisher tests and dashboard validation.

## Evidence and feedback verification

After the Render secret change has deployed, use the public chat or operator UI to
complete a real request and submit one rating. Confirm its redacted row appears in
`/control`, then run `check` after allowing Datadog ingestion time. It requires
positive `cognition.requests` and `feedback.responses` datapoints for this service
within the last hour. It exits 1 on missing signals and 2 on configuration/API errors.
These two signals prove recent metric delivery, not that a particular request's
feedback was persisted; that evidence remains in the Shared Spine and `/control`.

Missing data stays missing: no zero-filling or synthetic success traffic is used.
Latency is emitted as a gauge, so charts deliberately do not claim p95/p99. Evidence
readiness gauges update when the API readiness route is queried. Readiness remains
advisory and never starts training, changes routing, or promotes a model.

**Setup evidence (2026-10-22):** Pup OAuth published dashboard `qkr-8e7-6jg` in
`datadoghq.com`. The dedicated API intake key was installed in Render service
`srv-dasd3ajbc2fs73eos5jg` with matching secret readback. Activation deployment and
indexed request/feedback signals remain separate checks; publication is not E2E proof.
Activation deploy `dep-dbd6nl8n74is73aicds0` subsequently failed at startup because
`DUAL_LINEAGE_RAG_URL` is missing for the configured Ruby backend. The previous
service still responds to `/health`. The installed intake key passed Datadog's
validation endpoint (HTTP 200, `valid=true`), but runtime activation is unverified.
The initial CLI metric readback received HTTP 403; approve the corrected OAuth
grant containing `timeseries_query` before retrying `check`.
The admin console's
`datadog_configured` field only reports key presence. Its separate delivery state,
HTTP acceptance/rejection counters and timestamps expose intake behavior for the
responding API process. These reset on restart and do not prove metric indexing.
