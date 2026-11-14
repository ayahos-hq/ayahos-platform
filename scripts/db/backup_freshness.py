#!/usr/bin/env python3
"""Read-only encrypted archive freshness probe for trusted backup operators.

Object existence is not integrity, successful decryption, or verified recovery.
Do not activate a daily backup schedule before a real restore rehearsal.
"""
from __future__ import annotations

from datetime import UTC, datetime
import json
import os
import re
import subprocess
import sys


class FreshnessError(RuntimeError):
    """Safe-for-logs object-store health check failure."""


def check(env: dict[str, str], *, now: datetime | None = None) -> dict[str, object]:
    project = env.get("AYAHOS_BACKUP_PROJECT_REF", "").strip()
    remote = env.get("AYAHOS_BACKUP_RCLONE_REMOTE", "").strip()
    hours = env.get("AYAHOS_BACKUP_MAX_AGE_HOURS", "30").strip()
    if not re.fullmatch(r"[a-z]{20}", project):
        raise FreshnessError("invalid backup project identity")
    if (
        not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]*:[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*",
            remote,
        )
        or remote.split(":", 1)[0].lower() in {"local", "file", "ftp", "sftp"}
        or any(
            segment in {".", ".."}
            for segment in remote.split(":", 1)[1].split("/")
        )
    ):
        raise FreshnessError("invalid private R2 remote")
    try:
        maximum = int(hours)
    except ValueError as exc:
        raise FreshnessError("invalid backup freshness threshold") from exc
    if maximum < 1 or maximum > 168:
        raise FreshnessError("freshness threshold must be 1 to 168 hours")
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        raise FreshnessError("timezone-aware UTC clock required")

    # R2 listing requires object-store credentials only, not a database login.
    safe_env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"DATABASE_URL", "AYAHOS_BACKUP_DATABASE_URL"}
        and not key.startswith("PG")
    }
    result = subprocess.run(
        ["rclone", "lsjson", "--files-only", remote],
        env=safe_env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        check=False, timeout=45,
    )
    if result.returncode != 0 or len(result.stdout) > 4 * 1024 * 1024:
        raise FreshnessError("private backup object listing failed")
    try:
        items = json.loads(result.stdout)
    except (ValueError, UnicodeDecodeError) as exc:
        raise FreshnessError("unrecognized backup listing") from exc
    if not isinstance(items, list):
        raise FreshnessError("unrecognized backup listing")

    newest = None
    pattern = re.compile(
        rf"ayahos-{project}-(\d{{8}}T\d{{6}}Z)-[0-9a-f]{{8}}\.dump\.age"
    )
    for item in items:
        if not isinstance(item, dict) or item.get("IsDir", False):
            continue
        name = item.get("Path", "")
        if not isinstance(name, str):
            continue
        match = pattern.fullmatch(name)
        if not match or not isinstance(item.get("Size"), int) or item["Size"] <= 0:
            continue
        try:
            dated = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(
                tzinfo=UTC
            )
        except ValueError:
            continue
        age = (current - dated).total_seconds() / 3600
        # A copied archive or forged future timestamp cannot appear fresh.
        if age < -(10 / 60):
            continue
        if newest is None or dated > newest[0]:
            newest = (dated, name, item["Size"], age)

    if newest is None:
        raise FreshnessError("no qualifying encrypted backup archive found")
    if newest[3] > maximum:
        raise FreshnessError("newest encrypted backup is stale")
    return {
        "status": "fresh", "project_ref": project,
        "archive": newest[1], "encrypted_bytes": newest[2],
        "age_hours": round(max(newest[3], 0), 2), "max_age_hours": maximum,
        "integrity_verified": False, "restored": False,
    }


def main() -> int:
    try:
        print(json.dumps(check(dict(os.environ)), sort_keys=True))
        return 0
    except (FreshnessError, OSError, subprocess.SubprocessError) as exc:
        safe = str(exc) if isinstance(exc, FreshnessError) else "backup listing command failed"
        print(f"AyahOS backup freshness: {safe}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
