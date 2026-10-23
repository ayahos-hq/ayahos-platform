"""Network-free regression tests for canonical-versus-HQ drift logic."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import subprocess

MODULE = Path(__file__).with_name("audit-repo-drift.py")
spec = importlib.util.spec_from_file_location("migration_drift", MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DriftRules(unittest.TestCase):
    def test_three_way_outcomes(self):
        base = {"apps/api/same.py": "a", "apps/api/monorepo.py": "b",
                "apps/api/hq.py": "c", "apps/api/conflict.py": "d"}
        mono = {**base, "apps/api/monorepo.py": "new-mono",
                "apps/api/conflict.py": "mono-conflict"}
        hq = {**base, "apps/api/hq.py": "new-hq",
              "apps/api/conflict.py": "hq-conflict",
              "apps/api/hq-added.py": "added"}
        result = module.diff(base, mono, hq, ("apps/api/",))
        found = {entry["path"]: entry["kind"] for entry in result}
        self.assertEqual(found, {
            "apps/api/monorepo.py": "monorepo_only",
            "apps/api/hq.py": "hq_only",
            "apps/api/conflict.py": "both_diverged",
            "apps/api/hq-added.py": "hq_only",
        })

    def test_outside_owner_scope_is_ignored(self):
        self.assertEqual(module.diff({"apps/web/a": "one"},
                                     {"apps/web/a": "two"}, {}, ("apps/api/",)), [])

    def test_deletions_and_unchanged(self):
        found = module.diff({"apps/api/deleted.py": "a", "apps/api/stable.py": "b"},
                            {"apps/api/stable.py": "b"},
                            {"apps/api/deleted.py": "a", "apps/api/stable.py": "b"},
                            ("apps/api/",))
        self.assertEqual(found[0]["kind"], "monorepo_only")

    def test_truncated_tree_rejected(self):
        reader = module.GitHubReader("fake-only")
        reader.get = Mock(return_value={"truncated": True, "tree": []})
        with self.assertRaisesRegex(ValueError, "Incomplete Git tree"):
            reader.tree("test/repo", "a" * 40)

    def test_gh_operator_login_reads_json_without_token(self):
        reader = module.GitHubReader("", auth="gh")
        result = subprocess.CompletedProcess([], 0, '{"object":{"sha":"abc"}}', "")
        with patch.object(module.subprocess, "run", return_value=result) as run:
            response = reader.get("ayahos-hq/ayahos-site/git/ref/heads/main")
        self.assertEqual(response["object"]["sha"], "abc")
        args = run.call_args.args[0]
        self.assertEqual(args, ["gh", "api", "repos/ayahos-hq/ayahos-site/git/ref/heads/main"])
        self.assertNotIn("token", str(run.call_args).lower())

    def test_gh_error_never_leaks_private_response(self):
        reader = module.GitHubReader("", auth="gh")
        result = subprocess.CompletedProcess([], 1, "", "private token and account details")
        with patch.object(module.subprocess, "run", return_value=result):
            with self.assertRaises(ValueError) as caught:
                reader.get("ayahos-hq/ayahos-site/git/ref/heads/main")
        self.assertNotIn("private token", str(caught.exception))

    def test_gh_invalid_json_shape_fails_closed(self):
        reader = module.GitHubReader("", auth="gh")
        result = subprocess.CompletedProcess([], 0, "[]", "")
        with patch.object(module.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(ValueError, "invalid JSON"):
                reader.get("ayahos-hq/ayahos-site/git/ref/heads/main")

    def test_gh_missing_binary_fails_closed(self):
        reader = module.GitHubReader("", auth="gh")
        with patch.object(module.subprocess, "run", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(ValueError, "GitHub CLI"):
                reader.get("ayahos-hq/ayahos-site/git/ref/heads/main")

    def test_platform_ancestor_accepts_newer_nonidentical_head(self):
        reader = module.GitHubReader("fake-only")
        reader.get = Mock(return_value={"status": "ahead"})
        self.assertTrue(reader.is_ancestor("ayahos-hq/ayahos-platform", "a" * 40, "b" * 40))
        reader.get.assert_called_once_with(
            "ayahos-hq/ayahos-platform/compare/" + "a" * 40 + "..." + "b" * 40
        )

    def test_platform_diverged_or_unknown_ref_rejected(self):
        reader = module.GitHubReader("fake-only")
        for status in ("diverged", "behind", None):
            reader.get = Mock(return_value={"status": status})
            self.assertFalse(reader.is_ancestor("ayahos-hq/ayahos-platform", "a" * 40, "b" * 40))

    def test_platform_manifest_result_fails_on_nonancestor(self):
        reader = Mock()
        reader.head.side_effect = lambda repo: "c" * 40
        reader.tree.return_value = {}
        reader.is_ancestor.return_value = False
        manifest = {"source_commit": "b" * 40,
                    "components": {name: {"repository": "ayahos-hq/" + name,
                                           "git_sha": ("a" if name == "ayahos-platform" else "c") * 40}
                                   for name in module.PREFIXES}}
        result = module.audit(reader, manifest)
        self.assertFalse(result["components"]["ayahos-platform"]["head_matches_manifest"])

    def test_audit_never_attests_cutover_even_when_clean(self):
        r = Mock()
        r.head.side_effect = lambda repo: "c" * 40
        r.tree.return_value = {"apps/api/same.py": "a"}
        manifest = {"source_commit": "b" * 40,
                    "components": {name: {"repository": "ayahos-hq/" + name,
                                           "git_sha": "c" * 40}
                                   for name in module.PREFIXES}}
        report = module.audit(r, manifest)
        self.assertFalse(report["cutover_ready"])
        self.assertTrue(all(x["changed_paths"] == 0
                            for x in report["components"].values()))


if __name__ == "__main__":
    unittest.main()
