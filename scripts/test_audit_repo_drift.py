"""Network-free regression tests for canonical-versus-HQ drift logic."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock

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
