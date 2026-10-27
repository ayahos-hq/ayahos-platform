"""Read-only identity check for a Fly token supplied by a protected runner.

A valid identity is necessary but not sufficient for deploy or cost approval.
Never print command output, raw exceptions, or credential values.
"""
from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from typing import Mapping


def credential_probe(
    env: Mapping[str, str],
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> bool:
    value = env.get("FLY_API_TOKEN", "")
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        result = runner(
            ["flyctl", "auth", "whoami"],
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def main() -> int:
    passed = credential_probe(os.environ)
    print("FLY_STAGING_CREDENTIAL_PROBE=" + ("PASS" if passed else "DENY"))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
