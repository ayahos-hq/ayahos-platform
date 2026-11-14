"""Octopus owns operational backups; GitHub Actions must not run them."""
from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNBOOK = ROOT / ".octopus/runbooks/encrypted-database-backup.ocl"
SCRIPT = ROOT / "scripts/ci/octopus_db_backup.sh"


class OctopusBackupMigrationTests(unittest.TestCase):
    def test_github_backup_runner_is_removed(self):
        self.assertFalse((ROOT / ".github/workflows/encrypted-database-backup.yml").exists())

    def test_github_status_relay_runner_is_removed(self):
        self.assertFalse((ROOT / ".github/workflows/octopus-status-relay.yml").exists())

    def test_verification_lanes_remain_separate_from_secret_backup(self):
        process = (ROOT / ".octopus/deployment_process.ocl").read_text()
        self.assertIn('ScriptParameters = "api"', process)
        self.assertNotIn("octopus_db_backup.sh", process)
        self.assertNotIn("AYAHOS_BACKUP_DATABASE_URL", process)

    def test_runbook_matches_octopus_generated_root_and_nested_process(self):
        # Octopus server validated the Runbook root shape on an isolated branch.
        # The deployment-process format (a root-level step) is NOT a runbook.
        ocl = RUNBOOK.read_text(encoding="utf-8")
        self.assertTrue(ocl.startswith('name = "Encrypted database backup"'))
        self.assertIn('run_retention_policy {', ocl)
        self.assertIn('connectivity_policy {', ocl)
        self.assertIn('\nprocess {\n    step "encrypted-postgres-to-private-r2" {', ocl)
        self.assertNotIn('\nstep "encrypted-postgres-to-private-r2" {', ocl)
        self.assertIn('cancel_running_tasks = false', ocl)
        self.assertNotIn('AYAHOS_BACKUP_R2_SECRET_ACCESS_KEY', ocl)
        self.assertNotIn('DATABASE_URL = ', ocl)

    def test_runbook_is_not_a_ci_step_and_uses_dedicated_pool(self):
        ocl = RUNBOOK.read_text()
        self.assertIn('action_type = "Octopus.Script"', ocl)
        self.assertIn('worker_pool = "ayahos-backup"', ocl)
        self.assertIn('ScriptFileName = "scripts/ci/octopus_db_backup.sh"', ocl)
        self.assertNotIn("github", ocl.lower())
        self.assertNotIn("Octopus.Action.Script.ScriptBody", ocl)

    def test_octopus_gate_fails_closed_without_octopus_environment(self):
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            cwd=ROOT,
            env={"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp")},
            capture_output=True, text=True, timeout=10, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("postgresql://", result.stderr + result.stdout)

    def test_no_variable_substitution_or_db_credentials_in_git(self):
        runner = SCRIPT.read_text()
        self.assertIn("get_octopusvariable", runner)
        self.assertIn("AyahOS.Backup.RunApproved", runner)
        self.assertIn("RCLONE_CONFIG_AYAHOS_R2_SECRET_ACCESS_KEY", runner)
        self.assertNotIn("rclone config create", runner)
        self.assertNotIn("GITHUB_ENV", runner)
        self.assertNotIn("actions/checkout", runner)


    def test_octopus_only_manual_run_uses_in_memory_rclone_credentials(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tools = Path(tmp)
            ca = tools / "supabase-test-ca.pem"
            ca.write_text("FAKE CA TEST ONLY")
            getvar = tools / "get_octopusvariable"
            getvar.write_text(
                "#!/bin/sh\n"
                "case \"$1\" in\n"
                " AyahOS.Backup.RunApproved) echo YES;;\n"
                " AyahOS.Backup.RestoreGatePassed) echo YES;;\n"
                " AyahOS.Backup.DatabaseUrl) echo postgresql://fake:NONSECRET@db.example/postgres;;\n"
                " AyahOS.Backup.ProjectRef) echo xgomhbuzawoqnwlzvavx;;\n"
                " AyahOS.Backup.AgeRecipient) echo age1testrecipient;;\n"
                f" AyahOS.Backup.CAFile) echo {ca};;\n"
                " AyahOS.Backup.R2AccessKeyId) echo TEST_R2_ID;;\n"
                " AyahOS.Backup.R2SecretAccessKey) echo TEST_R2_SECRET;;\n"
                " *) exit 4;;\n"
                "esac\n"
            )
            dump = tools / "pg_dump"
            dump.write_text("#!/bin/sh\necho 'pg_dump (PostgreSQL) 17.11'\n")
            fake_python = tools / "python3"
            fake_python.write_text(
                "#!/bin/sh\n"
                "[ \"$1\" = scripts/db/backup_postgres.py ] || exit 7\n"
                "[ \"$RCLONE_CONFIG_AYAHOS_R2_SECRET_ACCESS_KEY\" = TEST_R2_SECRET ] || exit 8\n"
                "[ \"$AYAHOS_BACKUP_PROJECT_REF\" = xgomhbuzawoqnwlzvavx ] || exit 9\n"
                "echo '{\"status\":\"uploaded_verified\"}'\n"
            )
            # These are test-only presence stubs. The approved Octopus
            # backup worker must still provide real age and rclone binaries.
            # Fail the test if the mocked backup tries to execute either.
            for tool_name in ("age", "rclone"):
                guard = tools / tool_name
                guard.write_text("#!/bin/sh\necho unexpected-tool-invocation >&2\nexit 89\n")
                guard.chmod(0o700)
            for item in (getvar, dump, fake_python):
                item.chmod(0o700)
            env = {
                "PATH": f"{tools}:{os.environ['PATH']}",
                "HOME": os.environ.get("HOME", "/tmp"),
            }
            result = subprocess.run(
                ["bash", str(SCRIPT)], cwd=ROOT, env=env,
                capture_output=True, text=True, timeout=10, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("uploaded_verified", result.stdout)
            for secret in ("TEST_R2_SECRET", "NONSECRET"):
                self.assertNotIn(secret, result.stdout + result.stderr)

    def test_confirmation_without_recovery_gate_fails(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            provider = Path(tmp) / "get_octopusvariable"
            provider.write_text(
                "#!/bin/sh\n"
                'if [ "$1" = AyahOS.Backup.RunApproved ]; then echo YES; fi\n'
            )
            provider.chmod(0o700)
            env = {"PATH": f"{tmp}:{os.environ['PATH']}"}
            result = subprocess.run(
                ["bash", str(SCRIPT)], cwd=ROOT, env=env,
                capture_output=True, text=True, timeout=10, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("restore", result.stderr.lower())
            self.assertNotIn("postgresql://", result.stderr)


if __name__ == "__main__":
    unittest.main()
