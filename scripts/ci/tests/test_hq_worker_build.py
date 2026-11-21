"""HQ Worker Builds preview/production namespace isolation contract."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "check_hq_worker_build.py"
spec = importlib.util.spec_from_file_location("hq_worker_build_gate", SCRIPT)
assert spec and spec.loader
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class TestPreviewNamespaceSeparation(unittest.TestCase):
    def setUp(self) -> None:
        self.production = {
            "name": gate.EXPECTED_NAME,
            "main": gate.EXPECTED_SOURCE,
            "vars": {
                "GITHUB_REPOSITORY": gate.EXPECTED_REPO,
                "OCTOPUS_PROJECT": "AyahOS HQ Verification",
                "OCTOPUS_ENVIRONMENT": "Development",
                "STATUS_CONTEXT": "octopus/hq-operator-verified",
            },
            "kv_namespaces": [{"binding": "TASKS", "id": "49ce086dc87f4de9a5110e5771907cb3"}],
        }
        self.production["previews"] = {
            "vars": dict(self.production["vars"]),
            "kv_namespaces": [
                {"binding": "TASKS", "id": "2b5af79207114dec9989bc1d952c3c9d"}
            ],
        }

    def test_reviewed_root_production_and_distinct_preview_bindings_pass(self) -> None:
        gate.validate_config_data(self.production)

    def test_shared_production_namespace_in_preview_is_rejected(self) -> None:
        self.production["previews"]["kv_namespaces"] = self.production["kv_namespaces"]
        with self.assertRaisesRegex(ValueError, "isolated"):
            gate.validate_config_data(self.production)

    def test_unknown_production_namespace_is_rejected(self) -> None:
        self.production["kv_namespaces"][0]["id"] = "f" * 32
        with self.assertRaisesRegex(ValueError, "production"):
            gate.validate_config_data(self.production)

    def test_unknown_preview_namespace_is_rejected(self) -> None:
        self.production["previews"]["kv_namespaces"][0]["id"] = "f" * 32
        with self.assertRaisesRegex(ValueError, "preview"):
            gate.validate_config_data(self.production)

    def test_preview_cron_remains_prohibited(self) -> None:
        self.production["previews"]["triggers"] = {"crons": ["* * * * *"]}
        with self.assertRaisesRegex(ValueError, "cron"):
            gate.validate_config_data(self.production)


if __name__ == "__main__":
    unittest.main()
