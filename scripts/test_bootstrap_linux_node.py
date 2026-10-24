"""Fail-closed tests for the user-scoped, pinned Linux Node bootstrap."""
from __future__ import annotations

import os
from pathlib import Path
import platform
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "scripts" / "bootstrap-linux-node.sh"
VERSION = "22.23.4"


@unittest.skipUnless(
    platform.system() == "Linux" and platform.machine() == "x86_64",
    "Linux x86_64 integration fixture requires POSIX executable symlinks",
)
class NodeBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.target = self.home / ".local" / "opt" / f"node-v{VERSION}-linux-x64"
        self.links = self.home / ".local" / "bin"

    def run_bootstrap(self, mode: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(BOOTSTRAP), mode],
            env={**os.environ, "HOME": str(self.home)},
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    def fixture(self, reported_version: str) -> None:
        target_bin = self.target / "bin"
        target_bin.mkdir(parents=True)
        self.links.mkdir(parents=True)
        for executable in ("node", "npm", "npx", "corepack"):
            body = f"#!/bin/sh\nprintf '%s\\n' '{reported_version}'\n"
            file = target_bin / executable
            file.write_text(body)
            file.chmod(0o755)
            (self.links / executable).symlink_to(file)

    def test_check_does_not_create_missing_installation(self) -> None:
        result = self.run_bootstrap("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not installed", result.stderr)
        self.assertFalse((self.home / ".local").exists())

    def test_check_accepts_exact_pinned_runtime(self) -> None:
        self.fixture(f"v{VERSION}")
        result = self.run_bootstrap("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"Node v{VERSION}", result.stdout)

    def test_check_rejects_mismatched_runtime(self) -> None:
        self.fixture("v22.0.0")
        result = self.run_bootstrap("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Wrong Node version", result.stderr)

    def test_check_rejects_conflicting_binary_symlink(self) -> None:
        self.fixture(f"v{VERSION}")
        (self.links / "node").unlink()
        (self.links / "node").symlink_to(self.target / "bin" / "npm")
        result = self.run_bootstrap("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to overwrite", result.stderr)

    def test_check_refuses_root_identity_even_with_valid_node(self) -> None:
        self.fixture(f"v{VERSION}")
        stub_bin = self.home / "stubbin"
        stub_bin.mkdir()
        fake_id = stub_bin / "id"
        fake_id.write_text("#!/bin/sh\nif [ \"$1\" = '-u' ]; then echo 0; else /usr/bin/id \"$@\"; fi\n")
        fake_id.chmod(0o755)
        result = subprocess.run(
            ["bash", str(BOOTSTRAP), "--check"],
            env={**os.environ, "HOME": str(self.home),
                 "PATH": str(stub_bin) + os.pathsep + os.environ["PATH"]},
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Do not run as root", result.stderr)

    def test_install_refuses_to_replace_existing_user_executable(self) -> None:
        self.links.mkdir(parents=True)
        existing = self.links / "node"
        existing.write_text("DO_NOT_REPLACE")
        result = self.run_bootstrap("--install")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to overwrite", result.stderr)
        self.assertEqual(existing.read_text(), "DO_NOT_REPLACE")
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
