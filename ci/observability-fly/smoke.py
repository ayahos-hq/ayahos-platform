#!/usr/bin/env python3
"""Synthetic-only smoke for the private Fly OTLP collector and OSS stores.

Requires three operator-established loopback forwards and a protected bearer
token in the process environment. Never contacts Core or Datadog.
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

COLLECTOR = "http://127.0.0.1:14318"
PROMETHEUS = "http://127.0.0.1:19090"
LOKI = "http://127.0.0.1:13100"
COUNT = 200


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_LOOPBACK_OPENER = build_opener(ProxyHandler({}), _NoRedirects())


def _request(url: str, payload: dict[str, object], token: str | None) -> int:
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    request = Request(
        url,
        json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with _LOOPBACK_OPENER.open(request, timeout=5) as response:
            return response.status
    except HTTPError as exc:
        return exc.code


def _query(url: str) -> float:
    with _LOOPBACK_OPENER.open(url, timeout=4) as response:
        document = json.loads(response.read(256_000))
    if document.get("status") != "success":
        raise ValueError("backend query failed")
    results = document.get("data", {}).get("result", [])
    return sum(float(item["value"][1]) for item in results)


def _resource(name: str) -> dict[str, object]:
    return {"attributes": [
        {"key": "service.name", "value": {"stringValue": name}},
        {"key": "deployment.environment.name", "value": {"stringValue": "synthetic-staging"}},
    ]}


def _metric(name: str, timestamp: int) -> dict[str, object]:
    return {"resourceMetrics": [{
        "resource": _resource(name),
        "scopeMetrics": [{"scope": {"name": "ayahos.fly.smoke"}, "metrics": [{
            "name": "goblin.dual_lineage.cognition.requests",
            "sum": {
                "aggregationTemporality": 1,
                "isMonotonic": True,
                "dataPoints": [{
                    "startTimeUnixNano": str(timestamp - 1_000_000),
                    "timeUnixNano": str(timestamp),
                    "asDouble": 1.0,
                    "attributes": [{"key": "provider", "value": {"stringValue": "synthetic"}}],
                }],
            },
        }]}],
    }]}


def _logs(name: str, base_ns: int) -> dict[str, object]:
    return {"resourceLogs": [{
        "resource": _resource(name),
        "scopeLogs": [{"scope": {"name": "ayahos.fly.smoke"}, "logRecords": [{
            "timeUnixNano": str(base_ns + (i + 1) * 1_000_000),
            "severityNumber": 9,
            "severityText": "INFO",
            "body": {"stringValue": "ayahos.runtime.event"},
            "attributes": [{"key": "status", "value": {"stringValue": "synthetic"}}],
        } for i in range(COUNT)]}],
    }]}


def _token() -> str:
    token = os.environ.get("AYAHOS_OTLP_INGEST_TOKEN", "")
    if len(token) < 32 or not token.isascii() or any(ch.isspace() for ch in token):
        raise ValueError("missing or invalid protected collector token")
    return token


def main() -> int:
    token = _token()
    name = "ayahos-fly-smoke-" + secrets.token_hex(6)
    for path, empty in (
        ("/v1/metrics", {"resourceMetrics": []}),
        ("/v1/logs", {"resourceLogs": []}),
    ):
        if _request(COLLECTOR + path, empty, None) != 401:
            raise RuntimeError("collector did not reject unauthenticated " + path)

    base_ns = time.time_ns() - 10_000_000_000
    for i in range(COUNT):
        if _request(COLLECTOR + "/v1/metrics", _metric(name, base_ns + (i + 1) * 1_000_000), token) not in (200, 202, 204):
            raise RuntimeError("collector rejected authenticated synthetic metric")
    if _request(COLLECTOR + "/v1/logs", _logs(name, base_ns), token) not in (200, 202, 204):
        raise RuntimeError("collector rejected authenticated synthetic logs")

    promql = 'sum(goblin_dual_lineage_cognition_requests_total{service_name="' + name + '"})'
    logql = 'sum(count_over_time({service_name="' + name + '"}[5m]))'
    prom_url = PROMETHEUS + "/api/v1/query?query=" + quote(promql)
    loki_url = LOKI + "/loki/api/v1/query?query=" + quote(logql)
    deadline = time.monotonic() + 45
    metric_count = log_count = 0.0
    while time.monotonic() < deadline:
        try:
            metric_count = _query(prom_url)
            log_count = _query(loki_url)
        except (HTTPError, URLError, TimeoutError, ValueError, KeyError, IndexError):
            pass
        if abs(metric_count - COUNT) < 0.001 and abs(log_count - COUNT) < 0.001:
            print("PASS: private collector rejected anonymous writes and indexed 200 metrics/200 logs")
            return 0
        time.sleep(1)
    raise RuntimeError(f"private backend count mismatch (metrics={metric_count}, logs={log_count})")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, HTTPError, URLError, TimeoutError) as exc:
        # Never stringify network exceptions: request details may include auth.
        print("FAIL: private Fly staging smoke: " + str(exc) if isinstance(exc, (RuntimeError, ValueError)) else "FAIL: private Fly staging smoke: network unavailable", file=sys.stderr)
        raise SystemExit(1) from None
