"""Read-only operator report: Bayesian provider completion reliability.

This never changes the Overmind route, Undermind policy or provider health.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from dual_lineage.observability.provider_metrics import ProviderMetricsRecorder  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Advisory provider reliability evidence")
    parser.add_argument(
        "--path", default=os.getenv("DUAL_LINEAGE_PROVIDER_METRICS_PATH", "")
    )
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--min-samples", type=int, default=30)
    args = parser.parse_args(argv)

    if not args.path:
        print(json.dumps({"decision": "HOLD", "reason": "metrics_path_not_configured"}))
        return 2
    recorder = ProviderMetricsRecorder(
        path=Path(args.path),
        retention_hours=max(args.window_hours, 24),
    )
    status = recorder.status()
    estimates = recorder.reliability_estimates(
        window_hours=args.window_hours, min_samples=args.min_samples
    )
    print(json.dumps({
        "decision": "ADVISORY_ONLY",
        "persisted": status.persisted,
        "estimates": [item.model_dump(mode="json") for item in estimates],
        "note": "Per provider/model/route; workload mix not controlled; no automatic routing.",
    }, sort_keys=True))
    return 0 if estimates and all(x.evidence_status == "reviewable" for x in estimates) else 1


if __name__ == "__main__":
    raise SystemExit(main())
