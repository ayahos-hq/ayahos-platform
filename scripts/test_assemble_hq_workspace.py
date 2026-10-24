"""Offline regression checks for immutable five-repo HQ workspace assembly."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


MODULE = Path(__file__).with_name("assemble-hq-workspace.py")
spec = importlib.util.spec_from_file_location("assemble_hq", MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

COMPONENTS = ("ayahos-site", "ayahos-core", "ayahos-admin", "ayahos-platform", "ayahos-workloads")
SOURCE = "a" * 40
PLATFORM = "f" * 40


def candidate():
    return {
        "schema_version": 1, "release_status": "candidate",
        "source_authority": "fuaadabdullah/AyahOS_Dual_Lineage",
        "source_commit": SOURCE,
        "platform_manifest_commit_rule": "platform_git_sha_is_an_ancestor_of_manifest_commit",
        "components": {
            name: {"repository": "ayahos-hq/" + name, "git_sha": format(i + 1, "040x"),
                   "source_commit": SOURCE, "artifact_sha256": None}
            for i, name in enumerate(COMPONENTS)
        },
        "compatibility": {"api_contract": "python-authority-ruby-boundary-v1",
                          "database_schema": 23, "artifact_contract_status": "pending-independent-build",
                          "cross_repository_acceptance": "pending"},
        "acceptance": {"octopus_exact_sha": "pending", "database_restore_rehearsal": "pending",
                       "authenticated_live_smoke": "pending", "rollback_rehearsal": "pending"},
    }


class ReleaseAssemblerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.path = self.root / "release-manifest.json"
        self.path.write_text(json.dumps(candidate()))
        self.output = self.root / "workspace"

    def test_refs_are_exact_and_platform_ref_is_explicit(self):
        refs = module.refs(candidate(), PLATFORM)
        self.assertEqual(refs["ayahos-core"], "2".zfill(40))
        self.assertEqual(refs["ayahos-platform"], PLATFORM)
        self.assertEqual(len(refs), 5)

    def test_reject_non_candidate_or_forged_repo_before_cloning(self):
        for edit in (
            lambda m: m.update(release_status="released"),
            lambda m: m["components"]["ayahos-core"].update(repository="attacker/fork"),
            lambda m: m["components"]["ayahos-site"].update(artifact_sha256="a" * 64),
            lambda m: m["acceptance"].update(octopus_exact_sha="success"),
        ):
            m = candidate()
            edit(m)
            with self.assertRaises(ValueError):
                module.refs(m, PLATFORM)

    def test_requires_explicit_valid_platform_sha(self):
        for sha in ("", "main", "g" * 40, "a" * 39):
            with self.subTest(sha=sha), self.assertRaises(ValueError):
                module.refs(candidate(), sha)

    def test_existing_destination_cannot_be_overwritten(self):
        self.output.mkdir()
        with patch.object(module, "clone_at") as clone:
            with self.assertRaisesRegex(ValueError, "exists"):
                module.assemble(self.path, self.output, PLATFORM)
        clone.assert_not_called()

    def test_clone_failure_removes_partial_source_tree(self):
        def partial(repository, sha, where):
            where.mkdir()
            (where / "partial").write_text("partial")
            raise ValueError("clone failed, no tokens displayed")
        with patch.object(module, "clone_at", side_effect=partial), self.assertRaises(ValueError):
            module.assemble(self.path, self.output, PLATFORM)
        self.assertFalse(self.output.exists())
        self.assertEqual([x for x in self.root.iterdir() if x.name.startswith(".workspace-")], [])

    def test_mutated_platform_manifest_is_rejected(self):
        def fake_clone(repository, sha, where):
            where.mkdir()
            if repository.endswith("/ayahos-platform"):
                (where / "release-manifest.json").write_text('{"fake":true}')
        with patch.object(module, "clone_at", side_effect=fake_clone):
            with self.assertRaisesRegex(ValueError, "manifest"):
                module.assemble(self.path, self.output, PLATFORM)
        self.assertFalse(self.output.exists())

    def test_all_five_clean_sources_verified_before_atomic_promotion(self):
        called = []
        def fake_clone(repository, sha, where):
            where.mkdir()
            called.append((repository, sha))
            if repository.endswith("/ayahos-platform"):
                (where / "release-manifest.json").write_bytes(self.path.read_bytes())
        with patch.object(module, "clone_at", side_effect=fake_clone), \
             patch.object(module, "verify") as verified:
            result = module.assemble(self.path, self.output, PLATFORM)
        self.assertEqual(len(called), 5)
        # Validate manifest shape before clone and exact workspace contents after clone.
        self.assertEqual(verified.call_count, 2)
        self.assertEqual(verified.call_args_list[0].args, (self.path, None))
        self.assertEqual(verified.call_args_list[1].args[0], self.path)
        self.assertEqual(result, self.output)
        evidence = json.loads((self.output / "CANDIDATE-SOURCE-EVIDENCE.json").read_text())
        self.assertFalse(evidence["cutover_ready"])
        self.assertEqual(evidence["platform_checkout_sha"], PLATFORM)
        self.assertEqual(len(evidence["component_checkout_shas"]), 5)


    def test_without_gh_cli_linux_git_clone_uses_https_and_immutable_sha(self):
        destination = self.root / "clone"
        with patch.object(module.shutil, "which", return_value=None), \
             patch.object(module.subprocess, "run") as run:
            run.return_value.returncode = 0
            module.clone_at("ayahos-hq/ayahos-core", "a" * 40, destination)
        self.assertEqual(run.call_count, 2)
        clone = run.call_args_list[0]
        self.assertEqual(
            clone.args[0],
            ["git", "clone", "--quiet", "--no-checkout",
             "https://github.com/ayahos-hq/ayahos-core.git", str(destination)],
        )
        self.assertEqual(clone.kwargs["env"]["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(clone.kwargs["env"]["GH_PROMPT_DISABLED"], "1")
        self.assertEqual(
            run.call_args_list[1].args[0],
            ["git", "-C", str(destination), "checkout", "--detach", "--quiet", "a" * 40],
        )

    def test_when_gh_cli_exists_preserves_existing_clone_contract(self):
        destination = self.root / "clone"
        with patch.object(module.shutil, "which", return_value="/usr/bin/gh"), \
             patch.object(module.subprocess, "run") as run:
            run.return_value.returncode = 0
            module.clone_at("ayahos-hq/ayahos-site", "a" * 40, destination)
        self.assertEqual(
            run.call_args_list[0].args[0],
            ["gh", "repo", "clone", "ayahos-hq/ayahos-site",
             str(destination), "--", "--quiet", "--no-checkout"],
        )

    def test_clone_never_accepts_unknown_repo_or_invalid_sha(self):
        with patch.object(module.subprocess, "run") as run:
            for repository, sha in (
                ("attacker/fork", "a" * 40),
                ("ayahos-hq/ayahos-core", "main"),
                ("ayahos-hq/ayahos-core", "a" * 39),
            ):
                with self.subTest(repository=repository, sha=sha), self.assertRaises(ValueError):
                    module.clone_at(repository, sha, self.root / "clone")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
