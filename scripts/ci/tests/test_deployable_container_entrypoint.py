"""Regression: Octopus container smoke must run from a Git archive without executable bits."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
ENTRYPOINT = ROOT / "scripts/ci/deployable-container-smoke.sh"


class DeployableContainerSmokeInvocationTests(unittest.TestCase):
    def test_deployable_image_uses_ruby_33_or_later_compatible_base(self):
        """Minitest 6 cannot bundle under Debian bookworm's Ruby 3.1."""
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("FROM python:3.15-slim-trixie@sha256:94d3426f1def7db4a106a232ac121bfd975393e5dfd40a619b955fae45fe7913", dockerfile)
        self.assertIn("ruby-full", dockerfile)
        self.assertIn("gem install bundler", dockerfile)
    def test_nonexecutable_shell_smoke_runs_via_interpreter(self):
        # The Octopus checkout can contain this test fixture as plain mode 0644.
        source = ENTRYPOINT.read_text(encoding="utf-8")
        commands = [
            line.strip()
            for line in source.splitlines()
            if line.startswith("SMOKE_BASE_URL=")
            and "scripts/ci/container-smoke.sh" in line
        ]
        self.assertEqual(len(commands), 1, "Expected exactly one runtime smoke invocation")

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            script = folder / "scripts/ci/container-smoke.sh"
            script.parent.mkdir(parents=True)
            marker = folder / "smoke-ran"
            script.write_text('#!/bin/sh\nprintf smoke-ran > "$SMOKE_MARKER"\n', encoding="utf-8")
            script.chmod(0o644)
            self.assertFalse(os.access(script, os.X_OK))

            env = os.environ.copy()
            env["SMOKE_MARKER"] = str(marker)
            result = subprocess.run(
                ["/bin/sh", "-c", commands[0]],
                cwd=folder,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(marker.read_text(encoding="utf-8"), "smoke-ran")


if __name__ == "__main__":
    unittest.main()
