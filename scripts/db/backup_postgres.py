#!/usr/bin/env python3
"""Produce an encrypted PostgreSQL public-schema backup on a trusted external host.

Do not run this in a web request, Render startup or public CI. Encrypted backup
material belongs at a separately approved off-site destination. No plaintext
dump file, credentials or encryption private key are written by this program.
"""
from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit

from postgres_env import isolated_postgres_environment


class BackupError(RuntimeError):
    """Sanitized operator-facing failure."""


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise BackupError(f"missing required setting: {name}")
    return value


def _validate_source(url: str, project_ref: str) -> dict[str, str]:
    """Reject misdirected Supabase or connection-string override URLs."""
    if not re.fullmatch(r"[a-z]{20}", project_ref):
        raise BackupError("invalid expected project reference")
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        user = unquote(parts.username or "")
        port = parts.port or 5432
        password = unquote(parts.password or "")
    except (ValueError, TypeError) as exc:
        raise BackupError("invalid PostgreSQL connection URL") from exc
    if (parts.scheme not in {"postgresql", "postgres"} or parts.query
            or parts.fragment or parts.path != "/postgres" or port != 5432):
        raise BackupError("source must be a direct or session PostgreSQL database connection")
    direct_users = {"postgres", "ayahos_backup"}
    pooler_users = {f"{role}.{project_ref}" for role in direct_users}
    direct = host == f"db.{project_ref}.supabase.co" and user in direct_users
    pooler = host.endswith(".pooler.supabase.com") and user in pooler_users
    if not (direct or pooler):
        raise BackupError("database project identity differs from expected source")
    return {
        "PGHOST": host, "PGPORT": str(port), "PGDATABASE": "postgres",
        "PGUSER": user, "PGPASSWORD": password,
        "PGSSLMODE": "verify-full", "PGCONNECT_TIMEOUT": "12",
    }


def _remote_destination(remote: str, filename: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*:[A-Za-z0-9_./-]+", remote):
        raise BackupError("target must be a configured non-local rclone remote:path")
    if ".." in remote.split(":", 1)[1].split("/"):
        raise BackupError("backup target may not traverse directories")
    return remote.rstrip("/") + "/" + filename



def _postgres_environment(connection: dict[str, str]) -> dict[str, str]:
    """Only libpq inputs are needed by pg_dump; storage credentials stay private."""
    env = isolated_postgres_environment(connection)
    return {
        key: value for key, value in env.items()
        if key != "DATABASE_URL"
        and not key.startswith(("RCLONE_", "R2_", "AWS_", "OCTOPUS_", "AYAHOS_BACKUP_"))
    }


def _age_environment() -> dict[str, str]:
    """Public-recipient encryption must not receive database or R2 credentials."""
    return {
        key: value for key, value in os.environ.items()
        if key != "DATABASE_URL"
        and not key.startswith(("PG", "RCLONE_", "R2_", "AWS_", "OCTOPUS_", "AYAHOS_BACKUP_"))
    }


def _rclone_environment() -> dict[str, str]:
    """Private object transport must not inherit database connection secrets."""
    return {
        key: value for key, value in os.environ.items()
        if key != "DATABASE_URL"
        and not key.startswith(("PG", "OCTOPUS_", "AYAHOS_BACKUP_"))
    }


def _encrypt_dump(connection_env: dict[str, str], recipient: str, destination: Path) -> None:
    with subprocess.Popen(
        ["pg_dump", "--format=custom", "--no-owner", "--no-acl", "--no-password", "--schema=public"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env=_postgres_environment(connection_env),
    ) as dump:
        assert dump.stdout is not None
        encryption = subprocess.run(
            ["age", "-r", recipient, "-o", str(destination)],
            stdin=dump.stdout, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, env=_age_environment(), check=False,
        )
        dump.stdout.close()
        if encryption.returncode != 0:
            dump.kill()
        dump_status = dump.wait()
    if (encryption.returncode != 0 or dump_status != 0
            or not destination.is_file() or destination.stat().st_size == 0):
        raise BackupError("database dump or encryption failed; no upload attempted")


def _verify_remote(local_file: Path, remote_file: str) -> None:
    with local_file.open("rb") as source:
        expected = hashlib.file_digest(source, "sha256").digest()
    hasher = hashlib.sha256()
    with subprocess.Popen(
        ["rclone", "cat", remote_file],
        env=_rclone_environment(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    ) as reader:
        assert reader.stdout is not None
        for block in iter(lambda: reader.stdout.read(1024 * 1024), b""):
            hasher.update(block)
        result = reader.wait()
    if result != 0 or hasher.digest() != expected:
        raise BackupError("remote backup readback mismatch; backup NOT verified")


def main() -> int:
    try:
        url = _required("DATABASE_URL")
        project = _required("AYAHOS_BACKUP_PROJECT_REF")
        recipient = _required("AYAHOS_BACKUP_AGE_RECIPIENT")
        remote = _required("AYAHOS_BACKUP_RCLONE_REMOTE")
        connection_env = _validate_source(url, project)
        if not re.fullmatch(r"age1[023456789acdefghjklmnpqrstuvwxyz]{20,}", recipient):
            raise BackupError("invalid age public encryption recipient")
        for command in ("pg_dump", "age", "rclone"):
            if not shutil.which(command):
                raise BackupError(f"missing backup executable: {command}")
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        filename = f"ayahos-{project}-{timestamp}-{os.urandom(4).hex()}.dump.age"
        destination = _remote_destination(remote, filename)
        os.umask(0o077)
        with tempfile.TemporaryDirectory(prefix="ayahos-backup-") as directory:
            encrypted = Path(directory) / filename
            _encrypt_dump(connection_env, recipient, encrypted)
            result = subprocess.run(
                ["rclone", "copyto", str(encrypted), destination],
                env=_rclone_environment(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )
            if result.returncode != 0:
                raise BackupError("off-site upload failed; backup NOT verified")
            _verify_remote(encrypted, destination)
            size = encrypted.stat().st_size
            with encrypted.open('rb') as source:
                digest = hashlib.file_digest(source, 'sha256').hexdigest()
        print(json.dumps({
            "status": "uploaded_verified", "project_ref": project,
            "archive": filename, "encrypted_bytes": size,
            "encrypted_sha256": digest,
        }, sort_keys=True))
        return 0
    except (BackupError, OSError, subprocess.SubprocessError) as exc:
        # Never copy subprocess stderr or the connection URL into an error report.
        message = str(exc) if isinstance(exc, BackupError) else "backup executable failed"
        print(f"AyahOS backup failed: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
