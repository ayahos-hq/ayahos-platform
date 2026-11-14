"""Run the mandatory local release-hardening checks.

This gate intentionally fails when PostgreSQL is not configured.  SQLite and
skipped integration tests are useful development evidence, but are not release
evidence for persistence, distributed rate limiting, or incident retention.
Any skipped test in a gate group fails the gate, and caller-supplied
``PYTEST_ADDOPTS`` cannot deselect tests.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
PYTEST_GROUPS = {
    "auth": ["apps/api/tests/test_cognition_api.py"],
    "statistical_evidence": [
        "apps/api/tests/test_benchmark_stats.py",
        "apps/api/tests/test_benchmark_runner.py",
        "apps/api/tests/test_statistical_evidence_gates.py",
        "apps/api/tests/test_statistical_evidence_cli.py",
    ],
    "timeout": [
        "apps/api/tests/test_interrupts.py",
        "apps/api/tests/test_streaming_runtime.py",
    ],
    "rate_limiting": [
        "apps/api/tests/test_rate_limit.py",
        "apps/api/tests/test_rate_limit_postgres.py",
    ],
    "grounding": ["apps/api/tests/test_rag.py", "apps/api/tests/test_rag_remote.py"],
    "postgres_persistence": [
        "apps/api/tests/test_database_migrations.py",
        "apps/api/tests/test_spine_postgres.py",
        "apps/api/tests/test_operational_postgres.py",
        "apps/api/tests/test_agent_postgres.py",
        "apps/api/tests/test_devpilot_tasks_postgres.py",
        "apps/api/tests/test_route_health_postgres.py",
    ],
    "incident_recovery": [
        "apps/api/tests/test_observability_runtime.py",
        "apps/api/tests/test_observability_postgres.py",
    ],
    # Provider routing/failover: policy, observe/enforce, fallback, streaming failures,
    # cancellation/timeout over HTTP, and the rollout status surface.
    "routing_failover": [
        "apps/api/tests/test_operational_route_gate_cli.py",
        "apps/api/tests/test_operational_route_gate.py",
        "apps/api/tests/test_shadow_route_gate_cli.py",
        "apps/api/tests/test_shadow_route_review.py",
        "apps/api/tests/test_route_optimization.py",
        "apps/api/tests/test_routing_policy.py",
        "apps/api/tests/test_routing_coordinator.py",
        "apps/api/tests/test_routing_fixes.py",
        "apps/api/tests/test_routing_rollout.py",
        "apps/api/tests/test_routing_fallback.py",
        "apps/api/tests/test_routing_api.py",
        "apps/api/tests/test_resilience_hardening.py",
        "apps/api/tests/test_provider_resilience.py",
        "apps/api/tests/test_live_smoke_script.py",
    ],
}


def gate_env() -> dict[str, str]:
    """Environment for gate subprocesses, without caller-supplied pytest options.

    ``PYTEST_ADDOPTS`` can carry ``-k``, ``-m`` or ``--deselect``. Deselected
    tests emit no JUnit ``<skipped>`` element, so they would drop required
    PostgreSQL cases while the group still passes.
    """
    env = dict(os.environ)
    if env.pop("PYTEST_ADDOPTS", None) is not None:
        print(
            "NOTE: ignoring PYTEST_ADDOPTS; the release gate runs every selected test."
        )
    return env


def run(label: str, args: list[str]) -> None:
    run_command(label, [sys.executable, *args])


def run_command(label: str, command: list[str]) -> None:
    print(f"\n== {label} ==")
    result = subprocess.run(command, cwd=ROOT, env=gate_env(), check=False)
    if result.returncode:
        raise SystemExit(f"release gate failed: {label} ({result.returncode})")


def skipped_tests(junit_path: Path) -> list[str]:
    """Return ``file::name`` for every skipped test case in a JUnit report."""
    tree = ElementTree.parse(junit_path)
    return [
        f"{case.get('classname', '')}::{case.get('name', '')}"
        for case in tree.iter("testcase")
        if case.find("skipped") is not None
    ]


def run_pytest(label: str, tests: list[str]) -> None:
    """Run a pytest group and fail if any test was skipped.

    A skipped PostgreSQL test exits 0, so a passing exit code alone is not
    release evidence. Every collected test in the gate must actually run.
    """
    with tempfile.TemporaryDirectory() as tmp:
        junit_path = Path(tmp) / "junit.xml"
        run(label, ["-m", "pytest", "-q", "-rs", f"--junitxml={junit_path}", *tests])
        skipped = skipped_tests(junit_path)
    if skipped:
        listing = "\n  ".join(skipped)
        raise SystemExit(
            f"release gate failed: {label} skipped {len(skipped)} test(s):\n  {listing}"
        )


def main() -> int:
    if not os.environ.get("TEST_DATABASE_URL", "").strip():
        print(
            "ERROR: TEST_DATABASE_URL is required for release-check; use scripts/verify-postgres.ps1 first."
        )
        return 2
    run_command("deployment inventory", ["ruby", "scripts/check_service_inventory.rb"])
    run(
        "statistical evidence Ruff lint",
        [
            "-m", "ruff", "check",
            "apps/api/src/dual_lineage/bench/gates.py",
        ],
    )
    for label, tests in PYTEST_GROUPS.items():
        run_pytest(label, tests)
    print(
        "\nRelease-hardening checks passed: auth, statistical evidence, timeout, rate limiting, grounding, PostgreSQL persistence, incident recovery, routing failover"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
