"""No-network regression tests for fail-closed scoped CLI identity checks."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPT = Path(__file__).parent / "hq" / "access_doctor.py"
spec = importlib.util.spec_from_file_location("access_doctor", SCRIPT)
doctor = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = doctor
spec.loader.exec_module(doctor)

HQ = "a" * 32
OTHER = "b" * 32


class AccessDoctorTests(unittest.TestCase):
    def test_cloudflare_wrong_account_fails_closed(self):
        def runner(cmd):
            self.assertEqual(cmd, ["wrangler", "whoami", "--profile", "ayahos-hq"])
            return doctor.CommandResult(0, "Account ID: " + OTHER)
        check = doctor.check_cloudflare(runner, HQ)
        self.assertEqual(check.status, "wrong_account")
        self.assertNotIn(OTHER, str(check))

    def test_cloudflare_expected_account_works(self):
        check = doctor.check_cloudflare(lambda _: doctor.CommandResult(0, "HQ " + HQ), HQ)
        self.assertEqual(check.status, "ready")

    def test_cloudflare_without_expected_id_is_not_verified(self):
        check = doctor.check_cloudflare(lambda _: doctor.CommandResult(0, OTHER), None)
        self.assertEqual(check.status, "needs_target")

    def test_cloudflare_missing_profile_is_not_authenticated(self):
        check = doctor.check_cloudflare(lambda _: doctor.CommandResult(1, "profile not found"), HQ)
        self.assertEqual(check.status, "not_authenticated")

    def test_github_expected_account_and_repo(self):
        cmds = []
        def runner(cmd):
            cmds.append(cmd)
            return doctor.CommandResult(0, "fuaadabdullah" if len(cmds) == 1 else "ayahos-hq/ayahos-platform")
        self.assertEqual(doctor.check_github(runner).status, "ready")
        self.assertEqual(len(cmds), 2)

    def test_github_wrong_principal_rejected(self):
        self.assertEqual(doctor.check_github(lambda _: doctor.CommandResult(0, "other")).status, "wrong_account")

    def test_octopus_login_banner_with_zero_exit_is_not_ready(self):
        banner = "To get started with the Octopus CLI, please login to your Octopus Server"
        self.assertEqual(doctor.check_octopus(lambda _: doctor.CommandResult(0, banner)).status,
                         "not_authenticated")

    def test_octopus_json_space_grants_read_only_evidence(self):
        result = doctor.check_octopus(
            lambda _: doctor.CommandResult(0, '[{"Id":"Spaces-1","Name":"Default"}]'))
        self.assertEqual(result.status, "ready_read_only")

    def test_no_tokens_enter_command_args_or_results(self):
        cmds = []
        def runner(cmd):
            cmds.append(cmd)
            return doctor.CommandResult(1, "API_KEY=secret-value", "token=secret-value")
        checks = [doctor.check_github(runner), doctor.check_cloudflare(runner, HQ),
                  doctor.check_octopus(runner)]
        self.assertTrue(all(isinstance(c, list) for c in cmds))
        self.assertNotIn("secret-value", str(cmds))
        self.assertNotIn("secret-value", str(checks))


if __name__ == "__main__":
    unittest.main()
