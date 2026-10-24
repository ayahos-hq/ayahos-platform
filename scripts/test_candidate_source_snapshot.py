"""Snapshot-consistency regression for the non-deployable HQ release candidate.

A historical drift report is evidence, not real-time attestation or cutover approval.
"""
from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CandidateSourceSnapshotTests(unittest.TestCase):
    def test_attached_drift_report_matches_the_candidate_manifest(self) -> None:
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
                self.assertEqual(entry["manifest_sha"], pinned["git_sha"])
                self.assertTrue(
                    entry["head_matches_manifest"],
                    "source pin must agree with verified audit head; platform may use an ancestor",
                )
        self.assertEqual(manifest["compatibility"]["cross_repository_acceptance"], "pending")
        self.assertEqual(manifest["acceptance"]["database_restore_rehearsal"], "pending")
        self.assertEqual(manifest["acceptance"]["authenticated_live_smoke"], "pending")
        self.assertEqual(manifest["acceptance"]["rollback_rehearsal"], "pending")


if __name__ == "__main__":
    unittest.main()
