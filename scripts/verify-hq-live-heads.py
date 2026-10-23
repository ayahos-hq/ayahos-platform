#!/usr/bin/env python3
"""Compare a candidate release manifest with authenticated GitHub main heads.

This operator-only audit uses the current gh login. It does not store a token,
alter repositories, or substitute for hosted Octopus acceptance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r"[0-9a-f]{40}\Z")


class AuditError(Exception):
    pass


def gh_json(path: str, label: str) -> dict:
    result = subprocess.run(
        ["gh", "api", path], capture_output=True, text=True, check=False
    )
    if result.returncode:
        # GitHub's error body can contain account details; report the target only.
        raise AuditError(f"could not read {label}; check gh login and repository access")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AuditError(f"invalid GitHub response for {label}") from exc
    if not isinstance(value, dict):
        raise AuditError(f"unexpected GitHub response for {label}")
    return value


def verify_offline(manifest_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/verify-release-manifest.py"),
         "--manifest", str(manifest_path)],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise AuditError(result.stderr.strip() or "offline manifest check failed")


def audit(manifest_path: Path) -> None:
    verify_offline(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mismatches = []
    for name, component in manifest["components"].items():
        repository = component["repository"]
        head = gh_json(f"repos/{repository}/commits/main", repository).get("sha")
        if not isinstance(head, str) or not SHA.fullmatch(head):
            raise AuditError(f"invalid main commit identity for {repository}")
        expected = component["git_sha"]
        if name == "ayahos-platform":
            comparison = gh_json(
                f"repos/{repository}/compare/{expected}...{head}", repository
            )
            if comparison.get("status") not in ("ahead", "identical"):
                mismatches.append(f"{name}: manifest SHA is not an ancestor of main")
            else:
                print(f"{name}: manifest SHA is an ancestor of main ({expected[:12]})")
        elif head != expected:
            mismatches.append(f"{name}: manifest {expected[:12]} != main {head[:12]}")
        else:
            print(f"{name}: exact main SHA verified ({head[:12]})")
    if mismatches:
        raise AuditError("live head mismatch:\n  " + "\n  ".join(mismatches))
    print("All five live HQ main heads match the candidate manifest rule.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "release-manifest.json")
    args = parser.parse_args()
    try:
        audit(args.manifest.resolve())
    except (AuditError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"HQ LIVE HEAD AUDIT FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
