"""Cross-repo Ruby RAG schema test overlay must only use exact verified HQ sources."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).with_name("prepare-hq-rag-overlay.py")
spec = importlib.util.spec_from_file_location("hq_rag_overlay", MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RagOverlayTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.work = self.root / "verified"
        self.work.mkdir()
        self.core = self.work / "ayahos-core" / "apps" / "api"
        self.sql = self.core / "src" / "dual_lineage" / "db" / "migrations"
        self.sql.mkdir(parents=True)
        (self.sql / "001_tables.sql").write_text("CREATE TABLE example(id int);")
        self.rag = self.work / "ayahos-workloads" / "apps" / "rag-ruby"
        (self.rag / "test").mkdir(parents=True)
        (self.rag / "test" / "migrated_schema_test.rb").write_text("RUBY-TEST-SOURCE\n")
        (self.rag / "Gemfile").write_text('source "https://rubygems.org"\n')
        self.manifest = self.root / "release-manifest.json"
        self.manifest.write_text('{"schema_version": 1}')
        self.out = self.root / "overlay"

    def prepare(self):
        with patch.object(module, "verify") as verification:
            result = module.prepare(self.manifest, self.work, self.out)
        verification.assert_called_once_with(self.manifest, self.work)
        return result

    def test_overlay_links_verified_api_migrations_to_copied_ruby_tests(self):
        path = self.prepare()
        self.assertEqual(path, self.out)
        test_dir = self.out / "apps" / "rag-ruby" / "test"
        resolved = (test_dir / ".." / ".." / "api" / "src" / "dual_lineage" / "db" /
                    "migrations" / "001_tables.sql")
        self.assertEqual(resolved.read_text(), "CREATE TABLE example(id int);")
        self.assertEqual((test_dir / "migrated_schema_test.rb").read_text(), "RUBY-TEST-SOURCE\n")
        self.assertEqual((self.rag / "test" / "migrated_schema_test.rb").read_text(),
                         "RUBY-TEST-SOURCE\n")

    def test_missing_schema_source_fails_closed_before_output(self):
        (self.sql / "001_tables.sql").unlink()
        with self.assertRaisesRegex(ValueError, "SQL"):
            self.prepare()
        self.assertFalse(self.out.exists())

    def test_existing_target_is_never_overwritten(self):
        self.out.mkdir()
        (self.out / "keep").write_text("unchanged")
        with self.assertRaisesRegex(ValueError, "exists"):
            self.prepare()
        self.assertEqual((self.out / "keep").read_text(), "unchanged")

    def test_symlink_inside_rag_source_is_rejected(self):
        (self.rag / "test" / "external.rb").symlink_to(self.manifest)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.prepare()
        self.assertFalse(self.out.exists())

    def test_symlink_inside_core_sql_is_rejected(self):
        (self.sql / "999_external.sql").symlink_to(self.manifest)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.prepare()
        self.assertFalse(self.out.exists())

    def test_partial_copy_failure_leaves_no_workspace(self):
        with patch.object(module, "verify"):
            with patch.object(module.shutil, "copytree", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    module.prepare(self.manifest, self.work, self.out)
        self.assertFalse(self.out.exists())
        self.assertEqual(list(self.root.glob(".overlay-*")), [])

    def test_missing_verified_repo_fails_closed(self):
        (self.rag / "test" / "migrated_schema_test.rb").unlink()
        with self.assertRaisesRegex(ValueError, "RAG"):
            self.prepare()
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
