#!/usr/bin/env python3
"""Rehearse recovery of a private R2 ciphertext in an operator-provided local DB."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from restore_verify import target_environment, verify_restore


class RehearsalError(RuntimeError):
    """Error safe for operator logs; credentials are never included."""


def _required(env: dict[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise RehearsalError(f"missing required setting: {name}")
    return value


def rehearse(env: dict[str, str]) -> dict[str, object]:
    if _required(env, "AYAHOS_DISPOSABLE_RESTORE") != "1":
        raise RehearsalError("disposable restore acknowledgement required")
    project = _required(env, "AYAHOS_RESTORE_PROJECT_REF")
    remote = _required(env, "AYAHOS_RESTORE_RCLONE_REMOTE")
    archive = _required(env, "AYAHOS_RESTORE_ARCHIVE_NAME")
    expected = _required(env, "AYAHOS_RESTORE_SHA256").lower()
    identity = Path(_required(env, "AYAHOS_RESTORE_AGE_IDENTITY_FILE"))
    target = _required(env, "AYAHOS_RESTORE_DATABASE_URL")
    if not re.fullmatch(r"[a-z]{20}", project):
        raise RehearsalError("invalid expected project reference")
    if not re.fullmatch(
        r"[a-zA-Z0-9][a-zA-Z0-9_-]*:[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", remote
    ):
        raise RehearsalError("require an explicit nonlocal rclone remote:bucket/path")
    if remote.split(":", 1)[0].lower() in {"local", "file", "ftp", "sftp"} or any(
        part in {".", ".."} for part in remote.split(":", 1)[1].split("/")
    ):
        raise RehearsalError("encrypted archive source must be approved private object storage")
    match = re.fullmatch(
        r"ayahos-([a-z]{20})-(\d{8}T\d{6}Z)-([0-9a-f]{8})\.dump\.age", archive
    )
    if not match or match.group(1) != project:
        raise RehearsalError("encrypted backup filename does not match expected project")
    try:
        datetime.strptime(match.group(2), "%Y%m%dT%H%M%SZ")
    except ValueError as exc:
        raise RehearsalError("invalid backup timestamp") from exc
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise RehearsalError("encrypted SHA-256 checksum required")
    try:
        target_environment(target)
    except (ValueError, TypeError, RuntimeError) as exc:
        raise RehearsalError("invalid disposable PostgreSQL target") from exc
    if (
        not identity.is_file()
        or identity.is_symlink()
        or stat.S_IMODE(identity.stat().st_mode) & 0o077
    ):
        raise RehearsalError("private age identity must be a local owner-only regular file")

    with tempfile.TemporaryDirectory(prefix="ayahos-rehearsal-") as temporary:
        os.chmod(temporary, 0o700)
        encrypted = Path(temporary) / archive
        permitted = {
            "PATH", "HOME", "USER", "LOGNAME", "TMPDIR", "TMP", "TEMP",
            "XDG_CONFIG_HOME", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR",
            "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
        }
        transfer_env = {
            key: value
            for key, value in os.environ.items()
            if key in permitted or key.startswith(("RCLONE_", "AWS_", "R2_"))
        }
        result = subprocess.run(
            ["rclone", "copyto", f"{remote}/{archive}", str(encrypted)],
            env=transfer_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=180,
        )
        if result.returncode != 0 or not encrypted.is_file() or encrypted.is_symlink():
            raise RehearsalError("encrypted object download failed")
        with encrypted.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected:
            raise RehearsalError("encrypted object checksum mismatch")
        verification = verify_restore(encrypted, expected, identity, target)
    return {
        **verification,
        "archive": archive,
        "project_ref": project,
        "disaster_recovery_complete": False,
        "note": "schema gate only; compare source and restored row counts separately",
    }


def main() -> int:
    try:
        print(json.dumps(rehearse(dict(os.environ)), sort_keys=True))
        return 0
    except (RehearsalError, OSError, subprocess.SubprocessError, ValueError) as exc:
        safe = str(exc) if isinstance(exc, RehearsalError) else "backup rehearsal command failed"
        print(f"AyahOS backup rehearsal: {safe}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
