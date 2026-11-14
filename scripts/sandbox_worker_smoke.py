"""Smoke-test a deployed sandbox worker through the API's own client.

Usage (secret from the environment, never the command line):
    DUAL_LINEAGE_SANDBOX_WORKER_URL=https://sandbox.example \
    DUAL_LINEAGE_SANDBOX_WORKER_SECRET=... \
    python scripts/sandbox_worker_smoke.py

Exits non-zero unless the worker runs code, blocks the network, and enforces a timeout.
Prints only statuses and numbers, never program output beyond the expected marker.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api" / "src"))

from dual_lineage.sandbox import (  # noqa: E402
    SandboxJobStatus,
    SandboxLimits,
    SandboxSettings,
    SandboxWorkerClient,
)

CHECKS = (
    ("runs_python", "print('ayahos-sandbox-ok')", SandboxLimits(), SandboxJobStatus.COMPLETED,
     "ayahos-sandbox-ok"),
    (
        "network_blocked",
        "import socket\ntry:\n    socket.create_connection(('1.1.1.1', 443), timeout=2)\n"
        "    print('CONNECTED')\nexcept OSError:\n    print('blocked')\n",
        SandboxLimits(),
        SandboxJobStatus.COMPLETED,
        "blocked",
    ),
    ("timeout_enforced", "while True:\n    pass", SandboxLimits(timeout_ms=1000),
     SandboxJobStatus.TIMEOUT, None),
)


async def main() -> int:
    client = SandboxWorkerClient(
        SandboxSettings(
            os.environ["DUAL_LINEAGE_SANDBOX_WORKER_URL"],
            os.environ["DUAL_LINEAGE_SANDBOX_WORKER_SECRET"],
        )
    )
    failures = 0
    for name, code, limits, expected, marker in CHECKS:
        result = await client.run_python(
            job_id=f"smoke-{name}-{uuid.uuid4().hex[:12]}", code=code, limits=limits
        )
        ok = result.status is expected and (marker is None or result.stdout.strip() == marker)
        failures += 0 if ok else 1
        print(json.dumps({
            "check": name,
            "ok": ok,
            "status": result.status.value,
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "runtime": result.runtime,
        }))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
