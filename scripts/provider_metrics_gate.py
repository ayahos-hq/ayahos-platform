"""Verify the retained provider-comparison window without changing routing.

This checks a local JSONL metrics store. The live check against a deployed API runs in the Ruby
worker: `ruby apps/ruby_worker/bin/goblin-workflow provider-metrics-gate --url=API_ROOT`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check whether retained provider metrics cover a comparable 24-hour window."
    )
    parser.add_argument(
        "--path",
        default=os.getenv("DUAL_LINEAGE_PROVIDER_METRICS_PATH", ""),
        help="JSONL metrics path; defaults to DUAL_LINEAGE_PROVIDER_METRICS_PATH",
    )
    parser.add_argument(
        "--retention-hours",
        type=int,
        default=int(os.getenv("DUAL_LINEAGE_PROVIDER_METRICS_RETENTION_HOURS", "168")),
    )
    args = parser.parse_args()
    if not args.path:
        print(
            "provider metrics gate: configure a durable metrics path; for a live API run "
            "`ruby apps/ruby_worker/bin/goblin-workflow provider-metrics-gate --url=API_ROOT`",
            file=sys.stderr,
        )
        return 2

    api_root = Path(__file__).resolve().parents[1] / "apps" / "api"
    sys.path.insert(0, str(api_root / "src"))
    from dual_lineage.observability.provider_metrics import ProviderMetricsRecorder

    recorder = ProviderMetricsRecorder(
        path=Path(args.path),
        retention_hours=args.retention_hours,
    )
    status = recorder.status()
    print(json.dumps(status.model_dump(mode="json"), sort_keys=True))
    if not status.comparable_24h:
        print(
            "provider metrics gate: insufficient comparable coverage; routing must remain unchanged",
            file=sys.stderr,
        )
        return 1
    print("provider metrics gate: comparable 24-hour provider window verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
