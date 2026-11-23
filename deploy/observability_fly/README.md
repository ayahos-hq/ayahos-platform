# AyahOS-HQ: private Fly 6PN observability alpha

**Scope:** Three dedicated, private Fly applications in the existing `ayahos`
organization, Virginia/IAD. Not inside the existing 512-MiB production Core.
This source is an opt-in next stage of
[Platform issue #68](https://github.com/ayahos-hq/ayahos-platform/issues/68).
No public IP, Fly Proxy service, authentication bypass, Datadog secret deletion
or production Core rollout is approved by this directory.

## Architecture

- `ayahos-otel-ingest.internal:4318`: official pinned OTel Collector Contrib,
  bearer-authenticated OTLP/HTTP JSON metrics and redacted logs; collector
  memory cap 128 MiB, Fly 256-MiB machine.
- `ayahos-otel-metrics.internal:9090`: Prometheus remote-write receiver,
  48h retention or 512MB disk cap, one persistent Fly volume, 256-MiB machine.
- `ayahos-otel-logs.internal:3100`: Loki TSDB v13, 48h retention, one persistent
  Fly volume, 512-MiB machine. No public service.
- Existing localhost-only desktop Grafana remains a lab tool, not the always-on
  production dashboard. Future Grafana must receive explicit private access and
  authentication; do not expose the query APIs to the Internet.

Three shared-CPU Machines, initially ~1 GiB aggregate VM memory plus provider
overhead. All components are single-instance, not HA. Initial Fly pricing should
be checked against the actual bill: 256+256+512 MiB, plus 1GB Prometheus and
2GB Loki persistent volumes and snapshot/bandwidth costs. No use of trial
Oracle or inference machines.

## Security

Fly organization 6PN provides encrypted intra-org networking and internal DNS.
No external ingress is configured. Receiver authenticates `Authorization: Bearer`
against `AYAHOS_OTLP_INGEST_TOKEN` supplied as a secret **only to the Collector**,
with a matching `AYAHOS_OTLP_BEARER_TOKEN` supplied to the approved Core release
when an authenticated production canary is authorized. Tokens must be at least
32 random ASCII bytes. Never include tokens, DD keys or authorization headers in
Git, command output, GitHub issues or diagnostic logs.

Loki and Prometheus are internal to the Fly organization's shared 6PN; they
have no independent user auth. A compromised service in the same Fly org may
be able to access these endpoints, so these stores accept **only bounded,
pre-redacted metadata** and are not approved for prompts, PII, or regulated
logs. Additional per-backend auth/isolation is required for higher-trust data.

The Core exporter must be a reviewed build that supports private `.internal`
HTTP over 6PN **only with a bearer token**, while still refusing arbitrary
cleartext remote hosts. Default telemetry remains unchanged and the rollback
mode is `AYAHOS_TELEMETRY_MODE=legacy`.

## Operator deployment sequence (separately authorized)

1. Run `python3 gate.py` and
   `python3 -m unittest discover -s tests -p 'test_*.py' -v` before provisioning.
2. Verify reviewed image digests and compatible collector authentication.
3. Create exactly three apps with `fly apps create <name> --org ayahos`.
   DO NOT allocate any public IP and DO NOT add `services` to Fly configs.
4. Create the `otel_metrics` volume (1 GiB) in `ayahos-otel-metrics` and
   `otel_logs` volume (2 GiB) in `ayahos-otel-logs`, both IAD.
   Snapshot retention and cost must be reviewed.
5. Set `AYAHOS_OTLP_INGEST_TOKEN` via Fly-managed secret on the Collector
   without logging/displaying it.
6. Deploy `metrics`, `logs`, then `collector` from each local directory with
   `fly deploy --app <app> --config fly.toml`. Verify exact images, running
   process, backend disk, IPv6 private listener and **zero public IPs**.
7. With `fly proxy` local private port forwards, send 200 synthetic counter
   updates and 200 redacted logs with and without the bearer token; require
   401 without token and actual 200/200 indexing with token. Confirm no
   collector route can be reached from the public internet. No real user data.
8. Once the current reviewed Core image and auth feature are deployed under
   HQ Octopus release authority, dual-export into the secured Fly collector
   before an OTLP-only production canary. Confirm same **real** metadata event
   indexed in Datadog AND OSS. Hold on any mismatch, latency regression,
   dropped records or missing deploy provenance.
9. Only after production parity and rollback rehearsal, use
   `AYAHOS_TELEMETRY_MODE=otlp` for the controlled cutover. Preserve historical
   Datadog settings/keys until the separate retention and deletion decision.

## Recovery

Stop the isolated Fly Collector app if it becomes noisy; this must not affect
the production Core API or existing Datadog path. Use a separate approved Fly
secret/OTLP endpoint rollback (`AYAHOS_TELEMETRY_MODE=legacy`) if a canary was
started. Do not delete persistent backend volumes or historic Datadog keys
during rollback. Core/Undermind governance and source provenance remain the
release authority. Collector `deltatocumulative` state resets on restart;
do not claim cumulative metric exactness across unplanned restarts without
independent reconciliation.

**No public Grafana and no trace pipeline** are created by this setup.
