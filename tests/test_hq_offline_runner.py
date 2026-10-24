"""Regression checks for the standalone Octopus HQ offline test runner."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "run-hq-offline-tests.py"
spec = importlib.util.spec_from_file_location("hq_offline_runner", MODULE)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class OfflineRunnerTests(unittest.TestCase):
    def test_octopus_source_digest_is_accepted_but_not_used_as_release_evidence(self):
        with patch.object(runner, "run_suites", return_value=0) as suites:
            self.assertEqual(runner.main(["A" * 64]), 0)
        suites.assert_called_once_with()

    def test_invalid_or_multiple_positional_arguments_fail_closed(self):
        for args in (["not-a-digest"], ["a" * 64, "b" * 64]):
            with self.subTest(args=args), self.assertRaises(SystemExit):
                runner.main(args)

    def test_both_test_directories_must_run_and_failures_are_not_ignored(self):
        outcomes = [subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 1)]
        with patch.object(runner.subprocess, "run", side_effect=outcomes) as execute:
            self.assertEqual(runner.run_suites(), 1)
        self.assertEqual(execute.call_count, 2)
        self.assertIn("scripts", str(execute.call_args_list[0]))
        self.assertIn("tests", str(execute.call_args_list[1]))


if __name__ == "__main__":
    unittest.main()
