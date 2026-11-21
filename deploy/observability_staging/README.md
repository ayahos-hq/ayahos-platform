# AyahOS observability: isolated OTLP staging lab

**Status: SOURCE ONLY. Not deployed, not connected to production, not release authority.**

This directory implements [Platform issue #68](https://github.com/ayahos-hq/ayahos-platform/issues/68)
and is compatible with the opt-in Core exporter in [Core PR #125](https://github.com/ayahos-hq/ayahos-core/pull/125).
Core's deterministic Undermind/Action Gateway, release gates and Datadog integration remain unchanged.

## What is included

- One OTLP/HTTP JSON receiver, **not gRPC**, with bounded queue and memory.
- Delta-to-cumulative conversion for count metrics before Prometheus remote write.
- Native OTLP/HTTP redacted log ingestion into Loki.
- Grafana with provisioned Prometheus and Loki data sources and anonymous login disabled.
- All four HTTP ports bound to **127.0.0.1 only**. No public DNS, ingress, authentication proxy or remote collector access is created.
- 48-hour sample retention for Loki and Prometheus (Prometheus also capped to 512MB), named persistent volumes, capped Docker logs.
- Synthetic-only smoke that sends 200 counter increments and 200 fixed log entries; no prompts, responses, request IDs or cloud provider credentials.

**No tracing pipeline.** Tempo, span instrumentation, trace correlation and dashboards for those
signals are separate follow-up tasks. The 200-record synthetic smoke is not proof
of Core-to-Datadog parity or production readiness.

## Prerequisites

Use a reviewed **isolated Linux staging host** with Docker Engine **28+**, Compose v2,
at least 4 GB available RAM and 8 GB disk free for this short-lived exercise.
The configured container memory caps total 2 GiB; host, Docker and filesystem
overhead remain separate. Do not install onto a production Fly instance, the
canonical Supabase database, Node 001 inference machine, or Oracle node without
first measuring/approving spare capacity. The 127.0.0.1 binding is important:
older Docker Engine releases could expose localhost-published ports to the L2
network; test firewall and remote reachability before inserting any real data.

### Supply reviewed immutable images

Do not use `latest` or a tag alone. Resolve each image's real digest from
your trusted registry, verify OS/architecture and license, and **check its
security update status** before supplying the following environment variables
in your private shell session:

- `AYAHOS_OTEL_COLLECTOR_IMAGE` — `otel/opentelemetry-collector-contrib:<reviewed-tag>@sha256:<actual-64-hex-digest>`
- `AYAHOS_PROMETHEUS_IMAGE` — `prom/prometheus:<reviewed-tag>@sha256:<actual-64-hex-digest>`
- `AYAHOS_LOKI_IMAGE` — `grafana/loki:<reviewed-tag>@sha256:<actual-64-hex-digest>`
- `AYAHOS_GRAFANA_IMAGE` — `grafana/grafana:<reviewed-tag>@sha256:<actual-64-hex-digest>`
- `AYAHOS_GRAFANA_ADMIN_PASSWORD_FILE` — absolute path to an outside-repo
  password file owned by the operator, mode 0600, never checked in

Examples of image discovery (these **do not** pin a digest by themselves):
`docker buildx imagetools inspect otel/opentelemetry-collector-contrib:<tag>`
and the corresponding command for each other image.

Do not create an `.env` inside the repository. Keep credentials in an approved
secret store or private host path. `docker compose config` may reveal environment
fields, so do not paste its full output in tickets or public logs.

## Start (authorized local staging only)

From this directory, with the five variables configured:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 gate.py
docker compose -f compose.yaml up -d
python3 smoke.py
```

`gate.py` checks the fully rendered Compose configuration **before starting**
any containers. It refuses mutable images, unknown services, public/unbound
published ports, excess privileges, unbounded memory, Docker socket mounts,
anonymous Grafana and inline admin passwords.

Use SSH port forwarding to view Grafana from another machine:
`ssh -N -L 3000:127.0.0.1:3000 <authorized-operator>@<staging-host>`
and open `http://127.0.0.1:3000` on that machine. Grafana is not public.

Core PR #125's `OTEL_EXPORTER_OTLP_ENDPOINT` must **not** be pointed
directly at the remote staging host. The exporter requires HTTPS for remote
destinations, while this Compose receiver is intentionally localhost-only.
A remote Core staging instance needs its own reviewed, authenticated, TLS
reverse proxy/private mesh network and reachable collector URL. That
connectivity is not delivered by this lab and must not be improvised using
a public port 4318.

## Verification before any production change

1. Run and record the 200-event synthetic smoke and query actual Prometheus
   and Loki data; check both are exactly 200 for the unique synthetic service.
2. Verify the four bound ports are unreachable from a different host;
   test rejected external collector writes (not just Compose render).
3. Only after a protected collector ingress is independently authorized,
   enable OTLP in **Core staging**, leave Datadog in place, then compare the
   same metadata-only events in both backends. Fail closed on missing data.
4. Inject collector HTTP 503, timeout, missing DNS, restart and saturation.
   Core policy, site chat and Datadog delivery must remain functional.
5. Check telemetry overhead (CPU, RAM, p95 latency), dropped requests,
   log cardinality, 48-hour retention/deletion, persistent disk consumption
   and real monthly operating cost.
6. Require Octopus exact-SHA, PostgreSQL/pgvector, auth/guest, production
   artifact identity, live E2E and rollback approvals **independently**.
   This lab must not promote itself or change the deployment authority.

## Teardown / rollback

From the lab directory:

```sh
docker compose -f compose.yaml down
```

This preserves named volumes by default. Destroy the staging synthetic
volumes only if separately authorized and confirmed disposable. If a staged
Core exporter was enabled, unset `OTEL_EXPORTER_OTLP_ENDPOINT` there and
redeploy the reviewed configuration. **Do not delete or disable Datadog**.

## Technical constraints

The single Collector is deliberately not HA. Its `deltatocumulative`
processor is stateful and, as of this design review, marked alpha upstream.
A collector restart can reset counts; repeated or out-of-order delta
intervals can cause undercounts. The Core exporter must emit valid contiguous
delta time intervals; synthetic smoke checks this input shape, and a dedicated
Core regression guards it. Successful OTLP HTTP 200/202 is an **intake ack**,
not proof that Grafana has indexed all data. For financial cost totals use
reconciled provider usage/invoices, not the sampled `cognition.cost_usd`
gauge alone.

References:
- OpenTelemetry Collector: https://opentelemetry.io/docs/collector/configuration/
- Delta converter: https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/deltatocumulativeprocessor
- Loki native OTLP: https://grafana.com/docs/loki/latest/send-data/otel/
- Grafana Docker secrets: https://grafana.com/docs/grafana/latest/setup-grafana/configure-docker/
- Docker localhost published ports: https://docs.docker.com/engine/network/port-publishing/
