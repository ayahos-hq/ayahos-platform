#!/usr/bin/env python3
"""Collect bounded, content-free evidence for the physical Node 001 proof.

This is an observation tool. It never starts, stops, registers, or reconfigures
a node, and it never writes credentials, prompts, or model output to its evidence
file. The node-offline and fallback proof deliberately remains a separately
authorized operational step.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _request(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 20.0,
) -> tuple[int, Any, float]:
    body = None
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        raw = error.read()
        status = error.code
    except (TimeoutError, urllib.error.URLError):
        return 0, {"response_type": "request_failed"}, round((time.perf_counter() - started) * 1000, 2)

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    try:
        data = json.loads(raw.decode() or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        data = {"response_type": "non_json"}
    return status, data, elapsed_ms


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _safe_node(data: dict[str, Any]) -> dict[str, Any]:
    return {
        key: data.get(key)
        for key in ("status", "node_id", "active_jobs", "max_concurrency", "models", "roles")
        if key in data
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-url", required=True, help="Node agent base URL")
    parser.add_argument("--inference-secret", required=True)
    parser.add_argument("--node-id", default="node-001")
    parser.add_argument("--model", required=True)
    parser.add_argument("--control-plane-url", help="Optional control-plane base URL")
    parser.add_argument("--operator-secret", help="Required with --control-plane-url")
    parser.add_argument("--output", default="evidence/node-001-e2e.json")
    parser.add_argument("--max-tokens", type=int, default=32)
    args = parser.parse_args()

    if args.control_plane_url and not args.operator_secret:
        parser.error("--operator-secret is required with --control-plane-url")
    if args.max_tokens <= 0:
        parser.error("--max-tokens must be positive")

    node_url = args.node_url.rstrip("/")
    request_id = f"node001-e2e-{uuid.uuid4().hex[:12]}"
    evidence: dict[str, Any] = {
        "schema": "node-001-physical-e2e-v1",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "commit_sha": _git_sha(),
        "node_id_expected": args.node_id,
        "request_id": request_id,
        "checks": {},
        "manual_follow_up": (
            "Stop Node 001 only under an approved runbook; then prove that the control plane "
            "marks it offline and uses deterministic fallback."
        ),
    }

    health_status, health_data, health_ms = _request(f"{node_url}/health")
    health = health_data if isinstance(health_data, dict) else {}
    evidence["checks"]["node_health"] = {
        "http_status": health_status,
        "latency_ms": health_ms,
        "passed": health_status == 200
        and health.get("status") == "ok"
        and health.get("node_id") == args.node_id,
        "node": _safe_node(health),
    }

    inference_status, inference, inference_ms = _request(
        f"{node_url}/inference",
        method="POST",
        token=args.inference_secret,
        payload={
            "job_id": request_id,
            "brain_role": "cognitive",
            "model": args.model,
            "prompt": "Reply with exactly: node-001-ok",
            "options": {"max_tokens": args.max_tokens, "temperature": 0},
        },
    )
    inference_data = inference if isinstance(inference, dict) else {}
    usage = inference_data.get("usage")
    evidence["checks"]["authenticated_inference"] = {
        "http_status": inference_status,
        "latency_ms": inference_ms,
        "passed": inference_status == 200 and isinstance(usage, dict),
        "model": inference_data.get("model"),
        "usage": usage if isinstance(usage, dict) else {},
        "tokens_per_second": inference_data.get("tokens_per_second"),
    }

    if args.control_plane_url:
        registry_status, registry_data, registry_ms = _request(
            f"{args.control_plane_url.rstrip('/')}/compute/nodes",
            token=args.operator_secret,
        )
        nodes = registry_data.get("nodes", registry_data) if isinstance(registry_data, dict) else registry_data
        node = (
            next(
                (item for item in nodes if isinstance(item, dict) and item.get("node_id") == args.node_id),
                None,
            )
            if isinstance(nodes, list)
            else None
        )
        evidence["checks"]["control_plane_registration"] = {
            "http_status": registry_status,
            "latency_ms": registry_ms,
            "passed": registry_status == 200 and node is not None,
            "node": _safe_node(node) if isinstance(node, dict) else {},
        }

    checks = evidence["checks"]
    evidence["passed"] = bool(checks["node_health"]["passed"] and checks["authenticated_inference"]["passed"])
    if "control_plane_registration" in checks:
        evidence["passed"] = bool(evidence["passed"] and checks["control_plane_registration"]["passed"])

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": evidence["passed"], "output": str(output), "request_id": request_id}))
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
