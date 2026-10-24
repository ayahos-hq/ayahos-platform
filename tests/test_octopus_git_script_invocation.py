"""Regression: Octopus Git-backed script execution supplies a 64-hex source digest."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'verify-release-manifest.py'


class OctopusGitScriptInvocationTests(unittest.TestCase):
    def invoke(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, text=True, capture_output=True)

    def test_octopus_supplied_source_digest_does_not_break_manifest_check(self):
        result = self.invoke('26A903F83A109DBD7130F9A25CE58DE5B89F7FB805A07BE28DA03AF232E1506F')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Verified candidate manifest', result.stdout)

    def test_unrecognized_positional_argument_is_rejected(self):
        result = self.invoke('not-an-octopus-source-digest')
        self.assertNotEqual(result.returncode, 0)

    def test_multiple_source_digests_are_rejected(self):
        result = self.invoke('a' * 64, 'b' * 64)
        self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
