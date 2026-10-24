"""Fail-closed Octopus Git-sourced release-manifest shell entrypoint tests."""
from pathlib import Path
import os
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "octopus" / "verify-release-manifest.sh"


class ManifestShellEntrypointTests(unittest.TestCase):
    def run_wrapper(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(WRAPPER), *args],
            cwd=ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )

    def test_accepts_no_injected_digest(self) -> None:
        result = self.run_wrapper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Verified candidate manifest", result.stdout)

    def test_accepts_one_injected_runner_sha256_and_ignores_it(self) -> None:
        result = self.run_wrapper("0123456789abcdef" * 4)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Verified candidate manifest", result.stdout)

    def test_rejects_unexpected_second_argument(self) -> None:
        result = self.run_wrapper("f" * 64, "extra")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid Octopus source digest arguments", result.stderr)

    def test_rejects_invalid_digest(self) -> None:
        for digest in ("not-a-sha", "g" * 64, "f" * 63, "--manifest"):
            with self.subTest(digest=digest):
                result = self.run_wrapper(digest)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Invalid Octopus source digest arguments", result.stderr)


if __name__ == "__main__":
    unittest.main()
