"""Fail-closed Octopus Git-sourced release-manifest shell entrypoint tests."""
from pathlib import Path
import os
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "octopus" / "verify-release-manifest.sh"
# Windows' system bash.exe launches WSL and cannot read native Windows paths.
# Git Bash accepts the same POSIX wrapper used by the hosted Ubuntu worker.
GIT_BASH = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe"
BASH = str(GIT_BASH) if os.name == "nt" and GIT_BASH.is_file() else "bash"


class ManifestShellEntrypointTests(unittest.TestCase):
    def run_wrapper(self, *args: str) -> subprocess.CompletedProcess[str]:
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                       "HQ_MANIFEST_PYTHON": Path(sys.executable).as_posix()}
        if os.name == "nt":
            # Git Bash must translate /c/... arguments for native Python.
            environment.pop("MSYS_NO_PATHCONV", None)
            environment.pop("MSYS2_ARG_CONV_EXCL", None)
        return subprocess.run(
            [BASH, WRAPPER.as_posix(), *args],
            cwd=ROOT,
            env=environment,
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
