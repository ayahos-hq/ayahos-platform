"""Read-only P5 operational routing evidence CLI. No rollout modifications."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from dual_lineage.operational_route_gate import (  # noqa: E402
    OperationalRouteOutcome,
    evaluate_operational_canary,
)
from dual_lineage.routing import WorkloadProfile  # noqa: E402

HEADER_KEYS = frozenset({
    "deployment_sha", "canary_percent", "persisted", "provenance_verified",
    "source", "outcomes", "evidence_sha256",
})
ROW_KEYS = frozenset({
    "request_token", "bucket", "cohort", "workload_profile", "route_key",
    "recorded_at", "deployment_sha", "policy_version", "completed",
    "latency_ms", "cost_usd", "policy_violation",
})


def _hash_report(report: dict) -> str:
    serialized = json.dumps(
        {k: v for k, v in report.items() if k != "evidence_sha256"},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _load(path: Path) -> tuple[dict, list[OperationalRouteOutcome]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != HEADER_KEYS:
        raise ValueError("invalid_artifact_schema")
    if not isinstance(data["evidence_sha256"], str) or (
        _hash_report(data) != data["evidence_sha256"]
    ):
        raise ValueError("evidence_digest_mismatch")
    if data["source"] != "shared_spine_join":
        raise ValueError("unsupported_evidence_source")
    if type(data["persisted"]) is not bool or type(data["provenance_verified"]) is not bool:
        raise ValueError("invalid_evidence_flags")
    if type(data["canary_percent"]) not in (int, float):
        raise ValueError("invalid_canary_percent")
    if not isinstance(data["outcomes"], list):
        raise ValueError("invalid_outcomes")
    rows = []
    for item in data["outcomes"]:
        if not isinstance(item, dict) or set(item) != ROW_KEYS:
            raise ValueError("invalid_terminal_schema")
        for key in ("request_token", "cohort", "workload_profile", "route_key",
                    "recorded_at", "deployment_sha", "policy_version"):
            if type(item[key]) is not str:
                raise ValueError("invalid_terminal_string")
        if type(item["bucket"]) is not int:
            raise ValueError("invalid_canary_bucket")
        for key in ("completed", "policy_violation"):
            if type(item[key]) is not bool:
                raise ValueError("invalid_terminal_boolean")
        for key in ("latency_ms", "cost_usd"):
            if type(item[key]) not in (int, float):
                raise ValueError("invalid_terminal_number")
        if item["cohort"] not in {"baseline", "canary"}:
            raise ValueError("invalid_cohort")
        rows.append(OperationalRouteOutcome(
            request_token=item["request_token"],
            bucket=item["bucket"],
            cohort=item["cohort"],
            workload_profile=WorkloadProfile(item["workload_profile"]),
            route_key=item["route_key"],
            recorded_at=datetime.fromisoformat(item["recorded_at"]),
            deployment_sha=item["deployment_sha"],
            policy_version=item["policy_version"],
            completed=item["completed"],
            latency_ms=item["latency_ms"],
            cost_usd=item["cost_usd"],
            policy_violation=item["policy_violation"],
        ))
    return data, rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review live canary evidence offline")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--expected-deployment-sha", required=True)
    parser.add_argument("--expected-canary-percent", type=float, required=True)
    args = parser.parse_args(argv)
    try:
        data, rows = _load(args.evidence)
        if data["deployment_sha"] != args.expected_deployment_sha:
            raise ValueError("deployment_sha_mismatch")
        if data["canary_percent"] != args.expected_canary_percent:
            raise ValueError("canary_percent_mismatch")
        verdict = evaluate_operational_canary(
            rows, canary_percent=data["canary_percent"],
            expected_deployment_sha=data["deployment_sha"],
            persisted=data["persisted"],
            provenance_verified=data["provenance_verified"],
        )
        print(json.dumps(asdict(verdict), sort_keys=True))
        return {"REVIEW_ADVANCE": 0, "HOLD": 1, "ROLLBACK": 3}[verdict.decision]
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        known = {
            "invalid_artifact_schema", "evidence_digest_mismatch",
            "unsupported_evidence_source", "invalid_evidence_flags",
            "invalid_canary_percent", "invalid_outcomes",
            "invalid_terminal_schema", "invalid_terminal_string",
            "invalid_canary_bucket", "invalid_terminal_boolean",
            "invalid_terminal_number", "invalid_cohort",
            "deployment_sha_mismatch", "canary_percent_mismatch",
        }
        reason = str(exc)
        print(json.dumps({
            "decision": "INVALID",
            "reason": reason if reason in known else "invalid_evidence",
            "authority": "advisory_only",
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
