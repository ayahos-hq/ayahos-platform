"""Linux-executed and provenance-hashed files must resolve to LF on every platform.

Git for Windows defaults to ``core.autocrlf=true``, which checks shell scripts out as CRLF; bash then
fails with ``syntax error near unexpected token`` on the carriage returns. ``.gitattributes`` pins LF
so a Windows checkout behaves like CI.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _eol(path: str) -> str:
    out = subprocess.check_output(["git", "check-attr", "eol", "--", path], cwd=ROOT, text=True)
    return out.strip().rsplit(": ", 1)[-1]


@pytest.mark.parametrize(
    "path",
    [
        "scripts/ci/verify.sh",
        "scripts/ci/test_database_guard.sh",
        ".octopus/deployment_process.ocl",
        "scripts/verify-platform.py",
        "deploy/cloudrun/cloudbuild.yaml",
        "release-manifest.json",
    ],
)
def test_linux_executed_files_are_pinned_to_lf(path: str) -> None:
    assert (ROOT / path).is_file()
    assert _eol(path) == "lf"


def test_committed_shell_scripts_have_no_carriage_returns() -> None:
    tracked = subprocess.check_output(["git", "ls-files", "-z", "--", "*.sh"], cwd=ROOT).decode()
    for name in filter(None, tracked.split("\0")):
        blob = subprocess.check_output(["git", "show", f":{name}"], cwd=ROOT)
        assert b"\r" not in blob, f"{name} is committed with CRLF"
