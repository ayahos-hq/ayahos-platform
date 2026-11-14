#!/usr/bin/env python3
"""Cross-platform, idempotent API development environment bootstrap."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV = ROOT / ".venv"


def commands(env: Path, *, verify: bool = True) -> list[list[str]]:
    python = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    result = [[sys.executable, "-m", "venv", str(env)]]
    result.append([str(python), "-m", "pip", "install", "-e", str(ROOT / "apps/api") + "[dev,control]"])
    if verify:
        result.append([str(python), "-m", "pip", "check"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV, help="Virtual environment directory")
    parser.add_argument("--no-check", action="store_true", help="Skip pip check (not recommended)")
    args = parser.parse_args()
    env = args.env.expanduser().resolve()
    if env == ROOT or ROOT in env.parents and env.name != ".venv":
        parser.error("Use a dedicated .venv directory, not a source directory")
    for command in commands(env, verify=not args.no_check):
        subprocess.run(command, cwd=ROOT, check=True)
    print(f"API environment ready: {env}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
