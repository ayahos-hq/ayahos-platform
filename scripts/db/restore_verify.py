#!/usr/bin/env python3
"""Verify an encrypted app-schema archive only in an empty, local disposable DB.

Never creates databases, drops schemas, connects to remote hosts, or writes
decrypted data to an intermediate file. Pre-provision the isolated test DB.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from urllib.parse import unquote, urlsplit

from postgres_env import isolated_postgres_environment


class RestoreError(RuntimeError):
    """Sanitized restore refusal."""


def target_environment(url: str) -> dict[str, str]:
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port or 5432
        database = unquote(parts.path.lstrip("/"))
        user = unquote(parts.username or "")
        password = unquote(parts.password or "")
    except (ValueError, TypeError) as exc:
        raise RestoreError("invalid isolated restore database URL") from exc
    if (parts.scheme not in ("postgresql", "postgres")
            or parts.query or parts.fragment
            or host not in ("localhost", "127.0.0.1", "::1")
            or port != 5432
            or not re.fullmatch(r"ayahos_restore_[a-z0-9_]{4,48}", database)
            or not user or "/" in parts.path.lstrip("/")):
        raise RestoreError("restore target must be an explicitly named localhost disposable database")
    return {
        "PGHOST": host, "PGPORT": str(port), "PGDATABASE": database,
        "PGUSER": user, "PGPASSWORD": password,
        "PGCONNECT_TIMEOUT": "5", "PGSSLMODE": "prefer",
    }


def _run(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, env=env, capture_output=True, check=False, timeout=30)


def verify_restore(archive: Path, expected_checksum: str, identity: Path,
                   target_url: str) -> dict[str, str | int]:
    if os.environ.get("AYAHOS_DISPOSABLE_RESTORE") != "1":
        raise RestoreError("AYAHOS_DISPOSABLE_RESTORE=1 acknowledgement required")
    env = isolated_postgres_environment(target_environment(target_url))
    if (not archive.is_file() or archive.is_symlink()
            or not identity.is_file() or identity.is_symlink()):
        raise RestoreError("archive and encryption identity must be regular local files")
    if stat.S_IMODE(identity.stat().st_mode) & 0o077:
        raise RestoreError("age identity file must be private to its owner")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_checksum):
        raise RestoreError("expected encrypted archive checksum required")
    with archive.open("rb") as source:
        actual_checksum = hashlib.file_digest(source, "sha256").hexdigest()
    if actual_checksum != expected_checksum:
        raise RestoreError("encrypted backup checksum mismatch")

    # A read-only guard. Never restore to a nonempty target.
    empty = _run(["psql", "--no-psqlrc", "--no-password", "-Atc",
                  "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname = 'public'"], env)
    if empty.returncode or empty.stdout.strip() != b"0":
        raise RestoreError("restore target is not empty or not reachable")

    with subprocess.Popen(
        ["age", "-d", "-i", str(identity), str(archive)],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    ) as decrypt:
        assert decrypt.stdout is not None
        restored = subprocess.run([
            "pg_restore", "--exit-on-error", "--single-transaction",
            "--no-owner", "--no-acl", "--no-password",
            "--dbname", env["PGDATABASE"],
        ], env=env, stdin=decrypt.stdout, stdout=subprocess.DEVNULL,
           stderr=subprocess.DEVNULL, check=False)
        decrypt.stdout.close()
        if restored.returncode:
            decrypt.kill()
        decrypt_status = decrypt.wait()
    if restored.returncode or decrypt_status:
        raise RestoreError("isolated restore failed; disposable target requires teardown")

    # The backup must contain contiguous migrations, not merely a ledger table.
    # Zero or noncontiguous history is not usable recovery evidence.
    version_sql = (
        "SELECT CASE WHEN count(*) >= 1 AND min(version) = 1 "
        "AND max(version) = count(*) THEN count(*) ELSE 0 END "
        "FROM public.dual_lineage_schema_migrations"
    )
    version_result = _run(
        ["psql", "--no-psqlrc", "--no-password", "-Atc", version_sql], env
    )
    if version_result.returncode or not version_result.stdout.strip().isdigit():
        raise RestoreError("restored schema migration ledger unavailable")
    versions = int(version_result.stdout.strip())
    if versions < 1:
        raise RestoreError("restored schema migration history is incomplete")

    # These core runtime / workflow / RAG tables must all be present and
    # protected by RLS. A restored archive with missing policy coverage must
    # never be reported as an isolated recovery success.
    protected_sql = (
        "SELECT count(*) FROM pg_catalog.pg_class c "
        "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') "
        "AND c.relrowsecurity AND c.relname IN "
        "('dual_lineage_spine_requests', 'dual_lineage_spine_events', "
        "'dual_lineage_spine_events_archive', 'ruby_workflow_jobs', "
        "'rag_documents', 'rag_chunks')"
    )
    protected = _run(
        ["psql", "--no-psqlrc", "--no-password", "-Atc", protected_sql], env
    )
    if protected.returncode or protected.stdout.strip() != b"6":
        raise RestoreError("restored critical tables or RLS protection are missing")

    # Schema v23 introduces server-owned customer history. A v23+ restore
    # without both RLS-protected tables must never be accepted as recovered.
    critical_rls_tables = 6
    if versions >= 23:
        conversation_rls_sql = (
            "SELECT count(*) FROM pg_catalog.pg_class c "
            "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') "
            "AND c.relrowsecurity AND c.relname IN "
            "('ayahos_conversations', 'ayahos_messages')"
        )
        conversation_rls = _run(
            ["psql", "--no-psqlrc", "--no-password", "-Atc", conversation_rls_sql], env
        )
        if conversation_rls.returncode or conversation_rls.stdout.strip() != b"2":
            raise RestoreError("restored customer history tables or RLS protection are missing")
        critical_rls_tables += 2
    return {
        "status": "isolated_restore_verified",
        "schema_migrations": versions,
        "critical_rls_tables": critical_rls_tables,
        "encrypted_sha256": actual_checksum,
        "target": "local_disposable",
    }


def main() -> int:
    try:
        archive = Path(os.environ["AYAHOS_RESTORE_ENCRYPTED_FILE"])
        checksum = os.environ["AYAHOS_RESTORE_SHA256"].lower()
        identity = Path(os.environ["AYAHOS_RESTORE_AGE_IDENTITY_FILE"])
        target = os.environ["AYAHOS_RESTORE_DATABASE_URL"]
        print(json.dumps(verify_restore(archive, checksum, identity, target), sort_keys=True))
        return 0
    except (KeyError, ValueError, RestoreError, OSError, subprocess.SubprocessError) as exc:
        message = str(exc) if isinstance(exc, RestoreError) else "restore preflight or external command failed"
        print(f"AyahOS restore verification: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
