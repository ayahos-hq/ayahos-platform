"""Snapshot-consistency regression for the non-deployable HQ release candidate.

A historical drift report is evidence, not real-time attestation or cutover approval.
"""
from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CandidateSourceSnapshotTests(unittest.TestCase):
    def test_historical_drift_report_remains_a_non_cutover_record(self) -> None:
        manifest = json.loads((ROOT / "release-manifest.json").read_text())
        relative_path = manifest["reconciliation_evidence"]["drift_audit_path"]
        report_path = ROOT / relative_path
        self.assertTrue(report_path.is_file(), "named drift report must exist")
        report = json.loads(report_path.read_text())
        self.assertEqual(report["schema_version"], 1)
        self.assertFalse(report["cutover_ready"])
        self.assertEqual(
            set(report["components"]), set(manifest["components"]),
            "snapshot must cover all five HQ components",
        )
        for name, pinned in manifest["components"].items():
            with self.subTest(name=name):
                entry = report["components"][name]
                self.assertEqual(entry["repository"], pinned["repository"])
                self.assertTrue(
                    entry["head_matches_manifest"],
                    "historical audit source record must remain internally consistent",
                )

    def test_current_observed_heads_match_the_candidate_manifest(self) -> None:
        manifest = json.loads((ROOT / "release-manifest.json").read_text())
        relative_path = manifest["reconciliation_evidence"]["observed_heads_path"]
        report_path = ROOT / relative_path
        self.assertTrue(report_path.is_file(), "current observed-heads record must exist")
        report = json.loads(report_path.read_text())
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["kind"], "observed-heads-refresh")
        self.assertFalse(report["cutover_ready"])
        for name, pinned in manifest["components"].items():
            with self.subTest(name=name):
                entry = report["repositories"][name]
                self.assertEqual(entry["repository"], pinned["repository"])
                self.assertEqual(entry["git_sha"], pinned["git_sha"])

    def test_live_acceptance_remains_pending(self) -> None:
        manifest = json.loads((ROOT / "release-manifest.json").read_text())
        self.assertEqual(manifest["compatibility"]["cross_repository_acceptance"], "pending")
        self.assertEqual(manifest["acceptance"]["database_restore_rehearsal"], "pending")
        self.assertEqual(manifest["acceptance"]["authenticated_live_smoke"], "pending")
        self.assertEqual(manifest["acceptance"]["rollback_rehearsal"], "pending")


if __name__ == "__main__":
    unittest.main()
