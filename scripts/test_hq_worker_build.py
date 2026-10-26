"""Fail-closed regression suite for the HQ verification Worker build boundary.

The Worker being checked differs from the monorepo production Octopus bridge.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "ci" / "check_hq_worker_build.py"
spec = importlib.util.spec_from_file_location("check_hq_worker_build", CHECKER)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class HQWorkerBuildTests(unittest.TestCase):
    def test_requires_exact_event_sha(self):
        good = "a" * 40
        self.assertEqual(module.validate_sha(good, good), good)
        for expected in (None, "", "main", "a" * 39, "A" * 40, "b" * 40):
            with self.subTest(expected=expected):
                with self.assertRaises(ValueError):
                    module.validate_sha(expected, good)

    def test_hq_config_is_not_monorepo_worker(self):
        config_path = ROOT / "deploy" / "hq-verification-bridge" / "wrangler.jsonc"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(config["name"], "ayahos-hq-verification-bridge")
        self.assertEqual(config["main"], "../octopus-github-bridge/src/worker.js")
        self.assertEqual(config["vars"]["GITHUB_REPOSITORY"], "ayahos-hq/ayahos-platform")
        self.assertEqual(config["vars"]["OCTOPUS_PROJECT"], "AyahOS HQ Verification")
        self.assertEqual(config["vars"]["OCTOPUS_ENVIRONMENT"], "Development")
        self.assertEqual(config["vars"]["STATUS_CONTEXT"], "octopus/hq-operator-verified")
        self.assertEqual(config["kv_namespaces"][0]["binding"], "TASKS")
        self.assertNotIn("REPLACE_WITH", json.dumps(config))
        self.assertNotIn("OCTOPUS_API_KEY", json.dumps(config))
        self.assertNotIn("GITHUB_STATUS_TOKEN", json.dumps(config))
        self.assertTrue((config_path.parent / config["main"]).is_file())

    def test_ci_check_rejects_missing_production_guard(self):
        good = "a" * 40
        with self.assertRaises(ValueError):
            module.validate_build_environment(
                {"WORKERS_CI": "1", "WORKERS_CI_COMMIT_SHA": good,
                 "WORKERS_CI_BRANCH": "main", "AYAHOS_PREVIEW_ONLY": "0"}, good)
        self.assertEqual(
            module.validate_build_environment(
                {"WORKERS_CI": "1", "WORKERS_CI_COMMIT_SHA": good,
                 "WORKERS_CI_BRANCH": "docs/check", "AYAHOS_PREVIEW_ONLY": "1"}, good),
            good,
        )

    def test_no_branch_checkout_or_worker_deploy_commands(self):
        config = (ROOT / "deploy" / "hq-verification-bridge" / "BUILD_COMMANDS.md").read_text()
        self.assertNotIn("git checkout", config)
        self.assertNotIn("wrangler deploy\n", config)
        self.assertIn("WORKERS_CI_COMMIT_SHA", config)
        self.assertIn("wrangler@4.152.0 preview", config)


if __name__ == "__main__":
    unittest.main()
