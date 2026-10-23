"""Fail-closed tests for the five-HQ repository source checkout release preflight."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

MODULE = Path(__file__).with_name("verify-release-manifest.py")
spec = importlib.util.spec_from_file_location("verify_hq_release", MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def git(path: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(path), *args],
                            check=True, capture_output=True, text=True)
    return result.stdout.strip()


class ExactHqCheckoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "workspaces"
        self.workspace.mkdir()
        self.source_sha = "a" * 40
        self.heads = {}
        for name in module.REPOSITORIES:
            repo = self.workspace / name
            repo.mkdir()
            subprocess.run(["git", "init", "-q", "-b", "main", str(repo)],
                           check=True, capture_output=True)
            git(repo, "config", "user.email", "test@invalid.example")
            git(repo, "config", "user.name", "CI Test")
            (repo / "tracked.txt").write_text(name + "\n")
            git(repo, "add", "tracked.txt")
            git(repo, "commit", "-qm", "first")
            self.heads[name] = git(repo, "rev-parse", "HEAD")
            # Simulate a stale remote-tracking branch even when checkout moves.
            git(repo, "update-ref", "refs/remotes/origin/main", self.heads[name])
        self.manifest = self.root / "manifest.json"
        self.save_manifest()

    def save_manifest(self):
        manifest = {
            "schema_version": 1, "release_status": "candidate",
            "source_commit": self.source_sha,
            "components": {
                name: {"repository": repo, "git_sha": self.heads[name],
                       "source_commit": self.source_sha, "artifact_sha256": None}
                for name, repo in module.REPOSITORIES.items()
            },
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
        self.manifest.write_text(json.dumps(manifest))

    def verify(self):
        module.verify(self.manifest, self.workspace)

    def test_exact_five_clean_checkout_shas_accepted(self):
        self.verify()

    def test_modified_checkout_cannot_pass_by_matching_stale_origin_main(self):
        target = self.workspace / "ayahos-core"
        (target / "tracked.txt").write_text("different committed source\n")
        git(target, "add", ".")
        git(target, "commit", "-qm", "tampered checkout")
        with self.assertRaisesRegex(ValueError, "HEAD differs"):
            self.verify()

    def test_dirty_tracked_file_rejected_even_with_correct_commit_sha(self):
        target = self.workspace / "ayahos-site"
        (target / "tracked.txt").write_text("uncommitted payload\n")
        with self.assertRaisesRegex(ValueError, "dirty|untracked"):
            self.verify()

    def test_untracked_source_rejected_even_with_correct_commit_sha(self):
        target = self.workspace / "ayahos-core"
        (target / "untracked.py").write_text("print('injected')\n")
        with self.assertRaisesRegex(ValueError, "dirty|untracked"):
            self.verify()

    def test_detached_pinned_checkout_without_origin_main_is_valid(self):
        for name in module.REPOSITORIES:
            target = self.workspace / name
            git(target, "update-ref", "-d", "refs/remotes/origin/main")
            git(target, "checkout", "--detach", "-q", self.heads[name])
        self.verify()

    def test_platform_pin_is_ancestor_of_actual_detached_checkout(self):
        platform = self.workspace / "ayahos-platform"
        (platform / "tracked.txt").write_text("new platform verification commit\n")
        git(platform, "add", ".")
        git(platform, "commit", "-qm", "new platform verifier")
        git(platform, "checkout", "--detach", "-q", "HEAD")
        git(platform, "update-ref", "-d", "refs/remotes/origin/main")
        # The platform pin is intentionally an older immutable ancestor, never
        # a substitute for checking the *actual* current checkout.
        self.verify()

    def test_symlink_outside_workspace_is_rejected(self):
        path = self.workspace / "ayahos-site"
        external = self.root / "external"
        path.rename(external)
        path.symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "outside workspace"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
