"""Regression checks for the standalone Octopus HQ offline test runner."""
import importlib.util
import contextlib
import io
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
            with self.subTest(args=args), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                runner.main(args)

    def test_both_test_directories_must_run_and_failures_are_not_ignored(self):
        outcomes = [subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 1)]
        with patch.object(runner.subprocess, "run", side_effect=outcomes) as execute, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(runner.run_suites(), 1)
        self.assertEqual(execute.call_count, 2)
        self.assertIn("scripts", str(execute.call_args_list[0]))
        self.assertIn("tests", str(execute.call_args_list[1]))

    def test_child_unittest_output_is_consolidated_in_standard_output(self):
        successful = subprocess.CompletedProcess([], 0, stdout="Ran 2 tests\\nOK\\n")
        with patch.object(runner.subprocess, "run", return_value=successful) as execute:
            self.assertEqual(runner.run_suites(), 0)
        self.assertEqual(execute.call_count, 2)
        self.assertEqual(execute.call_args.kwargs["stdout"], subprocess.PIPE)
        self.assertEqual(execute.call_args.kwargs["stderr"], subprocess.STDOUT)


if __name__ == "__main__":
    unittest.main()
