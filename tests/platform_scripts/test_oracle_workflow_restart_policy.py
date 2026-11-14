"""Fail-closed restart policy regression for Oracle Ruby workflow units.

Keeps invalid DB credentials from generating thousands of five-second retries.
This tests committed templates, not the deployment state of live VMs.
"""
from __future__ import annotations

import unittest
from configparser import ConfigParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_UNITS = (
    "goblin-workflow-worker.service",
    "goblin-workflow-scheduler.service",
)


class OracleWorkflowRestartPolicyTests(unittest.TestCase):
    def test_unavailable_queue_fails_closed_without_restart_storm(self) -> None:
        for name in WORKFLOW_UNITS:
            with self.subTest(service=name):
                path = REPO_ROOT / "deploy" / "oracle" / name
                unit = ConfigParser(interpolation=None, strict=False)
                unit.optionxform = str
                self.assertTrue(unit.read(path), f"missing unit: {path}")
                self.assertEqual(unit["Service"]["Restart"], "on-failure")
                self.assertGreaterEqual(int(unit["Service"]["RestartSec"]), 600)
                self.assertGreaterEqual(int(unit["Unit"]["StartLimitIntervalSec"]), 3600)
                self.assertLessEqual(int(unit["Unit"]["StartLimitBurst"]), 4)
                self.assertEqual(unit["Service"]["EnvironmentFile"], "/etc/goblin/workflow.env")
                self.assertIn("PGSSLMODE=require", path.read_text(encoding="utf-8"))

    def test_distinct_worker_scheduler_entrypoints_preserved(self) -> None:
        root = REPO_ROOT / "deploy" / "oracle"
        worker = (root / WORKFLOW_UNITS[0]).read_text(encoding="utf-8")
        scheduler = (root / WORKFLOW_UNITS[1]).read_text(encoding="utf-8")
        self.assertIn("goblin-workflow work", worker)
        self.assertIn("goblin-workflow schedule --poll-seconds=30", scheduler)


if __name__ == "__main__":
    unittest.main()
