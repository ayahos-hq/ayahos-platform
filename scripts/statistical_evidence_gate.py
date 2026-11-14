"""Validate a frozen paired benchmark artifact before human release review.

Only interprets case-level evidence. This CLI never touches the runtime's
Undermind control envelope, model promotion, or deployment permissions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from dual_lineage.bench import evaluate_gates  # noqa: E402
from dual_lineage.bench.models import BenchmarkReport, SystemMode  # noqa: E402
from dual_lineage.bench.summary import summarize  # noqa: E402

_SHA = re.compile(r"^[0-9a-f]{40}$")


def inspect_artifact(path: Path, expected_sha: str) -> tuple[int, dict[str, object]]:
    if not _SHA.fullmatch(expected_sha):
        return 2, {"decision": "INVALID", "reason": "invalid_expected_sha"}
    try:
        raw = path.read_bytes()
        report = BenchmarkReport.model_validate_json(raw)
    except (OSError, ValueError):
        return 2, {"decision": "INVALID", "reason": "invalid_benchmark_artifact"}
    if report.metadata.git_sha != expected_sha:
        return 2, {"decision": "INVALID", "reason": "artifact_sha_mismatch"}

    ids: set[str] = set()
    for pair in report.results:
        item = pair.case
        if (
            item.case_id in ids
            or pair.baseline.case_id != item.case_id
            or pair.dual_lineage.case_id != item.case_id
            or pair.baseline.category != item.category
            or pair.dual_lineage.category != item.category
            or pair.baseline.mode is not SystemMode.BASELINE
            or pair.dual_lineage.mode is not SystemMode.DUAL_LINEAGE
            or pair.baseline.execution_order == pair.dual_lineage.execution_order
        ):
            return 2, {"decision": "INVALID", "reason": "invalid_case_pairing"}
        ids.add(item.case_id)

    # Never trust the stored aggregate: calculate it again from the frozen cases.
    # Actual SHA/model/hardware attestations and label provenance still require
    # external verification; this utility establishes internal artifact coherence.
    computed = summarize(
        report.results, bootstrap_iterations=2000, seed=report.metadata.seed
    )
    verdict = evaluate_gates(computed)
    return (0 if verdict.passed else 1), {
        "decision": "PASS" if verdict.passed else "HOLD",
        "evidence_kind": "paired_benchmark_only",
        "expected_sha": expected_sha,
        "artifact_sha256": hashlib.sha256(raw).hexdigest(),
        "case_count": len(report.results),
        "summary_recomputed": True,
        "gates": verdict.model_dump(mode="json"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evidence-only statistical benchmark release gate"
    )
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args(argv)
    status, output = inspect_artifact(args.report, args.expected_sha)
    print(json.dumps(output, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
