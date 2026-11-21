"""Offline fail-closed gate for private Fly 6PN observability services.

No production tokens, infrastructure calls, or network access needed.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent

APPS = {
    "collector": ("ayahos-otel-ingest", 256, None),
    "metrics": ("ayahos-otel-metrics", 256, "/prometheus"),
    "logs": ("ayahos-otel-logs", 512, "/loki"),
}

PINNED_IMAGE = re.compile(r"^FROM [a-zA-Z0-9./:_-]+@sha256:[a-f0-9]{64}$", re.M)


def check_app(name: str, fly: dict, dockerfile: str) -> None:
    app_name, memory, volume = APPS[name]
    if fly.get("app") != app_name or fly.get("primary_region") != "iad":
        raise ValueError("wrong app or production region")
    if "http_service" in fly or "services" in fly or "statics" in fly:
        raise ValueError("public network service is forbidden")
    if fly.get("build", {}).get("dockerfile") != "Dockerfile":
        raise ValueError("unreviewed build source")
    vms = fly.get("vm")
    if not isinstance(vms, list) or len(vms) != 1:
        raise ValueError("one reviewed VM required")
    if vms[0] != {"cpu_kind": "shared", "cpus": 1, "memory_mb": memory}:
        raise ValueError("resource budget exceeded")
    mounts = fly.get("mounts", [])
    if volume is None and mounts:
        raise ValueError("collector volume forbidden")
    if volume is not None and (
        not isinstance(mounts, list)
        or len(mounts) != 1
        or mounts[0].get("destination") != volume
        or mounts[0].get("source") != ("otel_metrics" if name == "metrics" else "otel_logs")
    ):
        raise ValueError("persistent volume required")
    if len(PINNED_IMAGE.findall(dockerfile)) != 1:
        raise ValueError("immutable container digest required")


def validate() -> None:
    for name in APPS:
        folder = ROOT / name
        model = tomllib.loads((folder / "fly.toml").read_text(encoding="utf8"))
        dockerfile = (folder / "Dockerfile").read_text(encoding="utf8")
        check_app(name, model, dockerfile)

    collector = (ROOT / "collector" / "collector.yaml").read_text(encoding="utf8")
    for value in (
        "bearertokenauth/ingest:", "${env:AYAHOS_OTLP_INGEST_TOKEN}",
        'endpoint: "[::]:4318"', "authenticator: bearertokenauth/ingest",
        "extensions: [bearertokenauth/ingest]", "deltatocumulative: {}",
        "http://ayahos-otel-metrics.internal:9090/api/v1/write",
        "http://ayahos-otel-logs.internal:3100/otlp",
    ):
        if value not in collector:
            raise ValueError("collector security or pipeline contract changed")
    if "debug:" in collector or "logging:" in collector or "traces:" in collector:
        raise ValueError("no unrestricted event debug/traces in production collector")
    prometheus = (ROOT / "metrics" / "prometheus.yaml").read_text(encoding="utf8")
    if "scrape_configs: []" not in prometheus:
        raise ValueError("unexpected network scrapers")
    prom_docker = (ROOT / "metrics" / "Dockerfile").read_text(encoding="utf8")
    for flag in ("--web.enable-remote-write-receiver", "--storage.tsdb.retention.time=48h",
                 "--storage.tsdb.retention.size=512MB", "--web.listen-address=[::]:9090"):
        if flag not in prom_docker:
            raise ValueError("Prometheus intake/retention contract changed")
    loki = (ROOT / "logs" / "loki.yaml").read_text(encoding="utf8")
    for value in ('http_listen_address: "::"', "auth_enabled: false",
                  "retention_period: 48h", "retention_enabled: true", "ingestion_rate_mb: 2",
                  'grpc_listen_address: "::"'):
        if value not in loki:
            raise ValueError("Loki private ingress/retention contract changed")


if __name__ == "__main__":
    try:
        validate()
    except (OSError, KeyError, ValueError, TypeError, tomllib.TOMLDecodeError) as error:
        print("FLY PRIVATE OBSERVABILITY REJECTED: " + type(error).__name__, file=sys.stderr)
        raise SystemExit(1) from None
    print("Fly three-app private OSS telemetry contract verified (no public ingress).")
