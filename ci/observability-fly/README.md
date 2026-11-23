# Private Fly OTLP staging smoke

This CI overlay supports the staging-only acceptance check in
[Platform issue #68](https://github.com/ayahos-hq/ayahos-platform/issues/68).
The extracted files under `deploy/observability_fly/` are pinned by
`SOURCE-PROVENANCE.json`; this overlay does not alter that source.

On an authorized operator host, start each forward in its own terminal:

```sh
fly proxy 14318:4318 --bind-addr 127.0.0.1 --app ayahos-otel-ingest
fly proxy 19090:9090 --bind-addr 127.0.0.1 --app ayahos-otel-metrics
fly proxy 13100:3100 --bind-addr 127.0.0.1 --app ayahos-otel-logs
```

Supply the existing collector bearer token to the smoke process through a
protected environment variable named `AYAHOS_OTLP_INGEST_TOKEN`; keep the
value out of command arguments, shell history, chat, issues, and logs. From
this directory run `python3 smoke.py`, then stop the forwards. The script uses
fixed loopback addresses, requires 401 for unauthenticated metrics and logs,
sends 200 authenticated synthetic delta metrics and 200 metadata-only logs,
and requires exact 200/200 Prometheus and Loki counts. It makes no Core or
Datadog requests and is not real same-event production parity evidence.

Run offline checks with:

```sh
python3 ../../scripts/verify-platform.py
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
```
