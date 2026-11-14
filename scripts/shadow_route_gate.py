"""P4 read-only shadow-route evidence CLI; never changes live routing."""
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

from dual_lineage.routing import WorkloadProfile  # noqa: E402
from dual_lineage.shadow_route_review import (  # noqa: E402
    ShadowRoutePair,
    review_shadow_routes,
)

HEADER_KEYS = frozenset({
    "baseline_sha", "shadow_sha", "source_kind",
    "training_case_ids", "pairs", "evidence_sha256",
})
PAIR_KEYS = frozenset({
    "case_id", "workload_profile", "observed_at", "allowed_route_keys",
    "baseline_route_key", "shadow_route_key",
    "baseline_success", "shadow_success",
    "baseline_critical_failure", "shadow_critical_failure",
    "baseline_latency_ms", "shadow_latency_ms",
    "baseline_cost_usd", "shadow_cost_usd",
})


def _digest(content: dict[str, object]) -> str:
    canonical = json.dumps(
        {key: value for key, value in content.items() if key != "evidence_sha256"},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _parse_report(payload: object) -> tuple[dict, list[ShadowRoutePair]]:
    if not isinstance(payload, dict) or set(payload) != HEADER_KEYS:
        raise ValueError("invalid_report_schema")
    if not isinstance(payload["evidence_sha256"], str):
        raise ValueError("invalid_evidence_digest")
    if _digest(payload) != payload["evidence_sha256"]:
        raise ValueError("evidence_digest_mismatch")
    if not isinstance(payload["pairs"], list):
        raise ValueError("invalid_pairs")
    if not isinstance(payload["training_case_ids"], list) or not all(
        isinstance(key, str) for key in payload["training_case_ids"]
    ):
        raise ValueError("invalid_training_case_ids")
    pairs: list[ShadowRoutePair] = []
    for row in payload["pairs"]:
        if not isinstance(row, dict) or set(row) != PAIR_KEYS:
            raise ValueError("invalid_pair_schema")
        if not isinstance(row["allowed_route_keys"], list) or not all(
            isinstance(key, str) for key in row["allowed_route_keys"]
        ):
            raise ValueError("invalid_eligible_routes")
        for field in (
            "baseline_success", "shadow_success",
            "baseline_critical_failure", "shadow_critical_failure",
        ):
            if type(row[field]) is not bool:
                raise ValueError("invalid_outcome_boolean")
        for field in (
            "baseline_latency_ms", "shadow_latency_ms",
            "baseline_cost_usd", "shadow_cost_usd",
        ):
            if type(row[field]) not in (float, int):
                raise ValueError("invalid_numeric_measurement")
        if any(
            type(row[key]) is not str
            for key in (
                "case_id", "workload_profile", "observed_at",
                "baseline_route_key", "shadow_route_key",
            )
        ):
            raise ValueError("invalid_string_field")
        pairs.append(
            ShadowRoutePair(
                case_id=row["case_id"],
                workload_profile=WorkloadProfile(row["workload_profile"]),
                observed_at=datetime.fromisoformat(row["observed_at"]),
                allowed_route_keys=tuple(row["allowed_route_keys"]),
                baseline_route_key=row["baseline_route_key"],
                shadow_route_key=row["shadow_route_key"],
                baseline_success=row["baseline_success"],
                shadow_success=row["shadow_success"],
                baseline_critical_failure=row["baseline_critical_failure"],
                shadow_critical_failure=row["shadow_critical_failure"],
                baseline_latency_ms=row["baseline_latency_ms"],
                shadow_latency_ms=row["shadow_latency_ms"],
                baseline_cost_usd=row["baseline_cost_usd"],
                shadow_cost_usd=row["shadow_cost_usd"],
            )
        )
    return payload, pairs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only P4 held-out shadow review")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--expected-baseline-sha", required=True)
    parser.add_argument("--expected-shadow-sha", required=True)
    args = parser.parse_args(argv)

    try:
        raw = json.loads(args.report.read_text(encoding="utf-8"))
        metadata, cases = _parse_report(raw)
        if metadata["baseline_sha"] != args.expected_baseline_sha:
            raise ValueError("baseline_sha_mismatch")
        if metadata["shadow_sha"] != args.expected_shadow_sha:
            raise ValueError("shadow_sha_mismatch")
        decision = review_shadow_routes(
            cases,
            baseline_sha=metadata["baseline_sha"],
            shadow_sha=metadata["shadow_sha"],
            source_kind=metadata["source_kind"],
            training_case_ids=metadata["training_case_ids"],
        )
        print(json.dumps(asdict(decision), sort_keys=True))
        return 0 if decision.decision == "REVIEW" else 1
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        reason = str(exc)
        # Unexpected parser internals are never exposed in operator output.
        known = {
            "invalid_report_schema", "invalid_evidence_digest",
            "evidence_digest_mismatch", "invalid_pairs",
            "invalid_training_case_ids", "invalid_pair_schema",
            "invalid_eligible_routes", "invalid_outcome_boolean",
            "invalid_numeric_measurement", "invalid_string_field",
            "baseline_sha_mismatch", "shadow_sha_mismatch",
        }
        print(json.dumps({
            "decision": "INVALID",
            "reason": reason if reason in known else "invalid_artifact",
            "authority": "advisory_only",
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
