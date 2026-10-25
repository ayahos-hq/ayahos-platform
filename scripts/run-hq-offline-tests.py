#!/usr/bin/env python3
"""Run all platform offline regression tests on an Octopus Hosted Ubuntu worker.

A Git-backed Octopus script may receive one transport checksum positional
argument. This is not an artifact attestation and never overrides tests.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run_suites() -> int:
    failed = False
    for directory in ("scripts", "tests"):
        source = ROOT / directory
        if not source.is_dir() or not list(source.glob("test_*.py")):
            if directory == "tests":
                print("OFFLINE TEST NOTE: no optional root tests suite; script suites remain authoritative")
                continue
            print(f"OFFLINE TEST FAILURE: missing {directory} suite", file=sys.stderr)
            failed = True
            continue
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "unittest", "discover",
                 "-s", str(source), "-p", "test_*.py", "-v"],
                cwd=ROOT, check=False, timeout=180,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            if completed.stdout:
                print(completed.stdout, end='' if completed.stdout.endswith('\n') else '\n')
            if completed.returncode != 0:
                failed = True
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"OFFLINE TEST FAILURE: {directory}: {type(exc).__name__}", file=sys.stderr)
            failed = True
    if failed:
        print("HQ OFFLINE TESTS FAILED; candidate remains unverified", file=sys.stderr)
        return 1
    print("HQ OFFLINE TESTS PASSED; live acceptance gates remain pending")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("octopus_source_digest", nargs="?")
    args = parser.parse_args(argv)
    digest = args.octopus_source_digest
    if digest is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
        parser.error("Octopus Git source digest must be 64 hexadecimal characters")
    return run_suites()


if __name__ == "__main__":
    raise SystemExit(main())
