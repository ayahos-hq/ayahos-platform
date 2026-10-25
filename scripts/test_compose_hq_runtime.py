"""Regression tests for exact-SHA Core + Workloads context composition."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

MODULE_PATH = Path(__file__).with_name("hq").joinpath("compose-hq-runtime.py")
SPEC = importlib.util.spec_from_file_location("compose_hq_runtime", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)

NAMES = (
    "ayahos-site",
    "ayahos-core",
    "ayahos-admin",
    "ayahos-platform",
    "ayahos-workloads",
)


def run_git(path: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()


class ComposeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.heads: dict[str, str] = {}

        for name in NAMES:
            repo = self.workspace / name
            subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
            run_git(repo, "config", "user.email", "test@example.invalid")
            run_git(repo, "config", "user.name", "HQ Test")
            (repo / "README.md").write_text(name + "\n", encoding="utf-8")
            if name == "ayahos-core":
                (repo / "apps/api/src/dual_lineage").mkdir(parents=True)
                (repo / "apps/api/pyproject.toml").write_text(
                    "[project]\nname='test'\nversion='0'\n", encoding="utf-8"
                )
                (repo / "apps/api/src/dual_lineage/main.py").write_text(
                    "app = object()\n", encoding="utf-8"
                )
            if name == "ayahos-workloads":
                for relative in (
                    "apps/rag-ruby/Gemfile",
                    "apps/rag-ruby/config.ru",
                    "apps/control-ruby/Gemfile",
                    "apps/control-ruby/config.ru",
                    "apps/ruby_worker/Gemfile",
                    "apps/ruby_worker/bin/goblin-workflow",
                ):
                    path = repo / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("placeholder\n", encoding="utf-8")
            run_git(repo, "add", ".")
            run_git(repo, "commit", "-qm", "source")
            self.heads[name] = run_git(repo, "rev-parse", "HEAD")

        components = {
            name: {
                "repository": "ayahos-hq/" + name,
                "git_sha": self.heads[name],
                "source_commit": "a" * 40,
                "artifact_sha256": None,
            }
            for name in NAMES
        }
        manifest_data = {
            "schema_version": 1,
            "release_status": "candidate",
            "release_id": "test-candidate",
            "source_authority": "fuaadabdullah/AyahOS_Dual_Lineage",
            "platform_manifest_commit_rule": "platform_git_sha_is_an_ancestor_of_manifest_commit",
            "source_commit": "a" * 40,
            "components": components,
            "compatibility": {
                "api_contract": "python-authority-ruby-boundary-v1",
                "database_schema": 23,
                "artifact_contract_status": "pending-independent-build",
                "cross_repository_acceptance": "pending",
            },
            "acceptance": {
                "octopus_exact_sha": "pending",
                "database_restore_rehearsal": "pending",
                "authenticated_live_smoke": "pending",
                "rollback_rehearsal": "pending",
            },
        }
        self.manifest = self.root / "release-manifest.json"
        self.manifest.write_text(json.dumps(manifest_data, sort_keys=True) + "\n", encoding="utf-8")
        platform = self.workspace / "ayahos-platform"
        (platform / "release-manifest.json").write_bytes(self.manifest.read_bytes())
        run_git(platform, "add", "release-manifest.json")
        run_git(platform, "commit", "-qm", "candidate manifest")
        platform_head = run_git(platform, "rev-parse", "HEAD")
        self.heads["ayahos-platform"] = platform_head

        receipt = {
            "schema_version": 1,
            "cutover_ready": False,
            "manifest_sha256": hashlib.sha256(self.manifest.read_bytes()).hexdigest(),
            "platform_checkout_sha": platform_head,
            "component_checkout_shas": self.heads,
            "artifact_digests": "pending-independent-build",
            "octopus_and_live_acceptance": "pending",
        }
        (self.workspace / "CANDIDATE-SOURCE-EVIDENCE.json").write_text(
            json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8"
        )
        self.output = self.root / "context"

    def compose(self) -> None:
        with patch.object(MODULE.PREFLIGHT, "verify"):
            MODULE.compose(self.manifest, self.workspace, self.output)

    def test_composes_required_paths_and_provenance(self) -> None:
        self.compose()
        self.assertTrue((self.output / "apps/api/pyproject.toml").is_file())
        self.assertTrue((self.output / "apps/rag-ruby/Gemfile").is_file())
        self.assertTrue((self.output / "apps/control-ruby/Gemfile").is_file())
        startup = self.output / "scripts/start-hq-composite.sh"
        self.assertTrue(startup.stat().st_mode & 0o111)
        record = json.loads((self.output / "COMPOSITE-SOURCE-MANIFEST.json").read_text())
        self.assertEqual(record["checkout_shas"], self.heads)
        self.assertTrue(record["authority_contract"]["duplicate_authorities_forbidden"])

    def test_missing_workload_path_fails_closed(self) -> None:
        shutil.rmtree(self.workspace / "ayahos-workloads/apps/rag-ruby")
        with patch.object(MODULE.PREFLIGHT, "verify"):
            with self.assertRaisesRegex(ValueError, "required source directory"):
                MODULE.compose(self.manifest, self.workspace, self.output)
        self.assertFalse(self.output.exists())

    def test_symlink_in_selected_source_fails_closed(self) -> None:
        escape = self.workspace / "ayahos-core/apps/api/escape"
        escape.symlink_to(self.root / "outside")
        with patch.object(MODULE.PREFLIGHT, "verify"):
            with self.assertRaisesRegex(ValueError, "symlink"):
                MODULE.compose(self.manifest, self.workspace, self.output)
        self.assertFalse(self.output.exists())

    def test_existing_output_is_never_overwritten(self) -> None:
        self.output.mkdir()
        with patch.object(MODULE.PREFLIGHT, "verify"):
            with self.assertRaisesRegex(ValueError, "destination already exists"):
                MODULE.compose(self.manifest, self.workspace, self.output)


if __name__ == "__main__":
    unittest.main()
