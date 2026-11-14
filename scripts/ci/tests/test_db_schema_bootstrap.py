"""Regression suite: API startup must not mutate production PostgreSQL schemas."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
POLICY = ROOT / "scripts" / "db" / "schema_startup.sh"


class DatabaseStartupPolicyTests(unittest.TestCase):
    def check(self, *, mode: str = "postgres", env_name: str = "production",
              migrate: str = "false", url: str = "postgresql://secret:password@db.example/db"):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            fake = directory / "python"
            fake.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CAPTURE"\n')
            fake.chmod(0o700)
            capture = directory / "calls"
            settings = {
                **os.environ,
                "PATH": f"{directory}:{os.environ['PATH']}",
                "CAPTURE": str(capture),
                "DATABASE_URL": url,
                "DUAL_LINEAGE_DATABASE_MODE": mode,
                "DUAL_LINEAGE_ENV": env_name,
                "DUAL_LINEAGE_SCHEMA_AUTO_MIGRATE": migrate,
            }
            process = subprocess.run(
                ["bash", "-c", f'source "{POLICY}"; ayahos_prepare_schema'],
                env=settings, text=True, capture_output=True, timeout=8,
            )
            commands = capture.read_text().splitlines() if capture.exists() else []
            return process, commands

    def test_production_only_checks_schema(self):
        result, commands = self.check()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["-m dual_lineage.db check"], commands)

    def test_local_mode_never_contacts_database(self):
        result, commands = self.check(mode="local", url="")
        self.assertEqual(0, result.returncode)
        self.assertEqual([], commands)

    def test_postgres_requires_connection(self):
        result, commands = self.check(url="")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual([], commands)
        self.assertIn("DATABASE_URL is required", result.stderr)

    def test_production_auto_migrate_is_rejected(self):
        result, commands = self.check(migrate="true")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual([], commands)
        self.assertNotIn("password", result.stderr + result.stdout)

    def test_explicit_local_development_migrate(self):
        result, commands = self.check(migrate="true", env_name="development")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["-m dual_lineage.db migrate"], commands)

    def test_unknown_mode_is_refused(self):
        result, commands = self.check(mode="invalid")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual([], commands)

    def test_application_startup_never_passes_db_urls_in_process_arguments(self):
        launcher = (ROOT / "scripts" / "start-dual-lineage.sh").read_text()
        self.assertNotIn("--database-url", launcher)

    def test_db_url_is_not_exposed_in_command_argv_or_output(self):
        result, commands = self.check(url="postgresql://sensitive:value@db.example/db")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn("sensitive", str(commands) + result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
