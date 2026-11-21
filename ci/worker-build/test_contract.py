#!/usr/bin/env python3
"""Regression coverage for the read-only HQ Worker Builds verification overlay."""
from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = pathlib.Path(__file__).with_name("check.py")
CONFIG = ROOT / "deploy/hq-verification-bridge/wrangler.jsonc"

spec = importlib.util.spec_from_file_location("hq_worker_build_check", SCRIPT)
assert spec and spec.loader
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class WorkerBuildContractTests(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        self.sha = "a" * 40
        self.env = {
            "WORKERS_CI": "1",
            "WORKERS_CI_COMMIT_SHA": self.sha,
            "WORKERS_CI_BRANCH": "main",
            "AYAHOS_PREVIEW_ONLY": "1",
        }

    def test_current_pinned_config_is_valid_for_isolated_preview(self):
        self.assertNotEqual(
            self.cfg["kv_namespaces"][0]["id"],
            self.cfg["previews"]["kv_namespaces"][0]["id"],
        )
        guard.validate_config(self.cfg, ROOT)

    def test_preview_reusing_production_kv_is_rejected(self):
        bad = copy.deepcopy(self.cfg)
        bad["previews"]["kv_namespaces"] = copy.deepcopy(bad["kv_namespaces"])
        with self.assertRaisesRegex(ValueError, "preview.*production|production.*preview"):
            guard.validate_config(bad, ROOT)

    def test_missing_preview_kv_is_rejected(self):
        bad = copy.deepcopy(self.cfg)
        bad["previews"]["kv_namespaces"] = []
        with self.assertRaises(ValueError):
            guard.validate_config(bad, ROOT)

    def test_preview_authority_mutation_is_rejected(self):
        bad = copy.deepcopy(self.cfg)
        bad["previews"]["vars"]["GITHUB_REPOSITORY"] = "someone-else/repo"
        with self.assertRaises(ValueError):
            guard.validate_config(bad, ROOT)

    def test_unknown_bindings_are_rejected(self):
        bad = copy.deepcopy(self.cfg)
        bad["vars"]["EXTRA_OPERATOR_TOKEN"] = "unexpected-privilege"
        bad["previews"]["vars"]["EXTRA_OPERATOR_TOKEN"] = "unexpected-privilege"
        with self.assertRaises(ValueError):
            guard.validate_config(bad, ROOT)

    def test_wrong_script_authority_is_rejected(self):
        bad = copy.deepcopy(self.cfg)
        bad["main"] = "../../secret.js"
        with self.assertRaises(ValueError):
            guard.validate_config(bad, ROOT)

    def test_secret_material_is_rejected(self):
        bad = copy.deepcopy(self.cfg)
        bad["vars"]["OCTOPUS_API_KEY"] = "not-a-real-token"
        bad["previews"]["vars"]["OCTOPUS_API_KEY"] = "not-a-real-token"
        with self.assertRaises(ValueError):
            guard.validate_config(bad, ROOT)

    def test_injected_ci_sha_is_mandatory(self):
        guard.validate_build_environment(self.env, self.sha)
        bad = dict(self.env, WORKERS_CI_COMMIT_SHA="b" * 40)
        with self.assertRaises(ValueError):
            guard.validate_build_environment(bad, self.sha)

    def test_fail_closed_without_cloudflare_branch_even_with_exact_sha(self):
        bad = dict(self.env)
        bad.pop("WORKERS_CI_BRANCH")
        with self.assertRaises(ValueError):
            guard.validate_build_environment(bad, self.sha)

    def test_fail_closed_without_cloudflare_sha_even_with_branch(self):
        bad = dict(self.env)
        bad.pop("WORKERS_CI_COMMIT_SHA")
        with self.assertRaises(ValueError):
            guard.validate_build_environment(bad, self.sha)

    def test_fail_closed_without_preview_only(self):
        bad = dict(self.env)
        bad.pop("AYAHOS_PREVIEW_ONLY")
        with self.assertRaises(ValueError):
            guard.validate_build_environment(bad, self.sha)

    def test_fail_closed_outside_workers_builds(self):
        bad = dict(self.env, WORKERS_CI="0")
        with self.assertRaises(ValueError):
            guard.validate_build_environment(bad, self.sha)


if __name__ == "__main__":
    unittest.main()
