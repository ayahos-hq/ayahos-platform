"""Regression tests for Fly isolated OTLP/metrics/logs contract, stdlib only."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fly_otel_gate", ROOT / "gate.py")
assert spec and spec.loader
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class FlyObservabilityContractTests(unittest.TestCase):
    def model(self, name: str) -> dict:
        return tomllib.loads((ROOT / name / "fly.toml").read_text(encoding="utf8"))

    def dockerfile(self, name: str) -> str:
        return (ROOT / name / "Dockerfile").read_text(encoding="utf8")

    def test_checked_in_configs_pass_without_network(self) -> None:
        gate.validate()

    def test_each_private_app_has_no_public_services(self) -> None:
        for name in gate.APPS:
            with self.subTest(name=name):
                model = self.model(name)
                model["http_service"] = {"internal_port": 4318}
                with self.assertRaisesRegex(ValueError, "public"):
                    gate.check_app(name, model, self.dockerfile(name))

    def test_rejects_wrong_organization_target_and_region(self) -> None:
        model = self.model("collector")
        model["app"] = "stranger-app"
        with self.assertRaisesRegex(ValueError, "wrong app"):
            gate.check_app("collector", model, self.dockerfile("collector"))

    def test_rejects_increased_resource_budget(self) -> None:
        model = self.model("collector")
        model["vm"][0]["memory_mb"] = 2048
        with self.assertRaisesRegex(ValueError, "resource"):
            gate.check_app("collector", model, self.dockerfile("collector"))

    def test_rejects_mutable_collector_images(self) -> None:
        with self.assertRaisesRegex(ValueError, "immutable"):
            gate.check_app(
                "collector", self.model("collector"), "FROM otel/opentelemetry-collector-contrib:latest"
            )

    def test_rejects_missing_durable_backends(self) -> None:
        for name in ("metrics", "logs"):
            with self.subTest(name=name):
                model = self.model(name)
                model.pop("mounts", None)
                with self.assertRaisesRegex(ValueError, "volume"):
                    gate.check_app(name, model, self.dockerfile(name))


if __name__ == "__main__":
    unittest.main()
