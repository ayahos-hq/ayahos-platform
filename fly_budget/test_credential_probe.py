"""Fail-closed, read-only Fly credential probe tests (never print provider output)."""
import subprocess
import unittest
from unittest.mock import patch

from credential_probe import credential_probe


class CredentialProbeTests(unittest.TestCase):
    def test_missing_credential_skips_provider(self):
        observed = []
        ok = credential_probe({}, runner=lambda *a, **k: observed.append(a))
        self.assertFalse(ok)
        self.assertEqual(observed, [])

    def test_valid_session_checks_identity_without_deployment(self):
        observed = []
        def run(args, **kwargs):
            observed.append((args, kwargs))
            return subprocess.CompletedProcess(args, 0, stdout="account-info", stderr="")
        self.assertTrue(credential_probe({"FLY_API_TOKEN": "synthetic-test-credential"}, runner=run))
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0][0], ["flyctl", "auth", "whoami"])
        self.assertFalse(observed[0][1]["shell"] if "shell" in observed[0][1] else False)
        self.assertEqual(observed[0][1]["env"]["FLY_API_TOKEN"], "synthetic-test-credential")
        self.assertEqual(observed[0][1]["stdout"], subprocess.DEVNULL)
        self.assertEqual(observed[0][1]["stderr"], subprocess.DEVNULL)

    def test_invalid_credentials_fail_closed(self):
        def run(args, **kwargs):
            return subprocess.CompletedProcess(args, 1)
        self.assertFalse(credential_probe({"FLY_API_TOKEN": "synthetic-test"}, runner=run))

    def test_binary_missing_and_timeout_fail_closed(self):
        for exc in (OSError("missing"), subprocess.TimeoutExpired("flyctl", 10)):
            def run(args, **kwargs):
                raise exc
            self.assertFalse(credential_probe({"FLY_API_TOKEN": "synthetic-test"}, runner=run))

    def test_never_logs_credentials_or_provider_details(self):
        with patch("builtins.print") as print_mock:
            self.assertFalse(credential_probe({"FLY_API_TOKEN": "synthetic-test"}, runner=lambda *a, **k: subprocess.CompletedProcess(a[0], 1)))
        print_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
