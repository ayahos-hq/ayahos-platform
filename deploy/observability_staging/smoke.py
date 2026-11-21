#!/usr/bin/env python3
"""Synthetic-only, loopback-only OTLP -> Prometheus/Loki parity smoke.

No credentials, private content, external requests or production API calls.
Run only after the digest-pinned staging Compose services have started.
"""
from __future__ import annotations

import json
import secrets
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

COLLECTOR = "http://127.0.0.1:4318"
PROMETHEUS = "http://127.0.0.1:9090"
LOKI = "http://127.0.0.1:3100"


def _post(url: str, payload: dict[str, object]) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = Request(url, body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=5) as response:
        if response.status not in (200, 202, 204):
            raise RuntimeError("local collector refused synthetic telemetry")


def _query(url: str) -> float:
    with urlopen(url, timeout=4) as response:
        doc = json.loads(response.read(256_000))
    if doc.get("status") != "success":
        return -1.0
    results = doc.get("data", {}).get("result", [])
    if not results:
        return 0.0
    return sum(float(item.get("value", [0, "0"])[1]) for item in results)


def _resource(name: str) -> dict[str, object]:
    return {
        "attributes": [
            {"key": "service.name", "value": {"stringValue": name}},
            {"key": "deployment.environment.name", "value": {"stringValue": "synthetic-staging"}},
        ]
    }


def main() -> int:
    # Unique service for every run; no real user IDs or credentials appear in exported data.
    name = "ayahos-staging-" + secrets.token_hex(5)
    n = 200
    base_ns = time.time_ns() - 10_000_000_000
    resource = _resource(name)
    for i in range(n):
        end_ns = base_ns + (i + 1) * 1_000_000
        start_ns = base_ns + i * 1_000_000
        payload: dict[str, object] = {
            "resourceMetrics": [
                {
                    "resource": resource,
                    "scopeMetrics": [
                        {
                            "scope": {"name": "ayahos.staging.smoke"},
                            "metrics": [
                                {
                                    "name": "goblin.dual_lineage.cognition.requests",
                                    "sum": {
                                        "aggregationTemporality": 1,
                                        "isMonotonic": True,
                                        "dataPoints": [
                                            {
                                                "startTimeUnixNano": str(start_ns),
                                                "timeUnixNano": str(end_ns),
                                                "asDouble": 1.0,
                                                "attributes": [
                                                    {"key": "provider", "value": {"stringValue": "synthetic"}}
                                                ],
                                            }
                                        ],
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        _post(COLLECTOR + "/v1/metrics", payload)

    log_payload: dict[str, object] = {
        "resourceLogs": [
            {
                "resource": resource,
                "scopeLogs": [
                    {
                        "scope": {"name": "ayahos.staging.smoke"},
                        "logRecords": [
                            {
                                "timeUnixNano": str(base_ns + (i + 1) * 1_000_000),
                                "severityNumber": 9,
                                "severityText": "INFO",
                                "body": {"stringValue": "ayahos.runtime.event"},
                                "attributes": [
                                    {"key": "status", "value": {"stringValue": "synthetic"}}
                                ],
                            }
                            for i in range(n)
                        ],
                    }
                ],
            }
        ]
    }
    _post(COLLECTOR + "/v1/logs", log_payload)

    promql = 'sum(goblin_dual_lineage_cognition_requests_total{service_name="' + name + '"})'
    logql = 'sum(count_over_time({service_name="' + name + '"}[5m]))'
    prom_url = PROMETHEUS + "/api/v1/query?query=" + quote(promql)
    loki_url = LOKI + "/loki/api/v1/query?query=" + quote(logql)
    deadline = time.monotonic() + 45
    metrics_value = logs_value = 0.0
    while time.monotonic() < deadline:
        try:
            metrics_value = _query(prom_url)
            logs_value = _query(loki_url)
        except (HTTPError, URLError, ValueError, KeyError, json.JSONDecodeError):
            pass
        if abs(metrics_value - n) < 0.001 and abs(logs_value - n) < 0.001:
            print("PASS: synthetic OTLP metric sums and log count equal 200 in OSS backends")
            return 0
        time.sleep(1)
    print(
        "FAIL: local staging ingestion mismatch; review collector conversion and "
        f"backends (metric_count={metrics_value}, log_count={logs_value})",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        print("FAIL: staging-only loopback test unavailable: " + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1) from None
