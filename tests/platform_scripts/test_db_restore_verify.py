"""Offline regressions: restore only to a disposable local database."""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "db" / "restore_verify.py"


def _run(tmp_path: Path, *, url="postgresql://postgres@localhost/ayahos_restore_test01",
         empty=True, checksum=True, fail="", authorized=True, rls_count=6, migrations=21, conversation_rls_count=2):
    binaries = tmp_path / "bin"
    binaries.mkdir(exist_ok=True)
    commands = {
        "psql": """#!/bin/sh
[ "${FAIL_CMD:-}" != psql ] || exit 4
[ -z "${PGHOSTADDR:-}" ] || exit 44
[ -z "${PGSERVICE:-}" ] || exit 45
if [ "${EXPECT_EMPTY:-}" = 1 ]; then
  case "$*" in
    *pg_catalog.pg_tables*) printf '0\n'; exit 0;;
    *ayahos_conversations*) printf '%s\\n' "$FAKE_CONVERSATION_RLS_COUNT"; exit 0;;
    *pg_class*) printf '%s\n' "$FAKE_RLS_COUNT"; exit 0;;
    *dual_lineage_schema_migrations*) printf '%s\n' "$FAKE_SCHEMA_VERSIONS"; exit 0;;
  esac
  printf '21\n'
else
  printf '1\n'
fi
""",
        "age": """#!/bin/sh
[ "${FAIL_CMD:-}" != age ] || exit 5
printf 'PGDMP fake archive'
""",
        "pg_restore": """#!/bin/sh
[ "${FAIL_CMD:-}" != pg_restore ] || exit 6
cat >/dev/null
""",
    }
    for name, body in commands.items():
        tool = binaries / name
        tool.write_text(body)
        tool.chmod(0o700)
    archive = tmp_path / "backup.age"
    archive.write_bytes(b"encrypted test archive")
    identity = tmp_path / "identity.txt"
    identity.write_text("FAKE PRIVATE KEY")
    identity.chmod(0o600)
    env = {
        **os.environ, "PATH": f"{binaries}:{os.environ['PATH']}",
        "AYAHOS_RESTORE_DATABASE_URL": url,
        "AYAHOS_RESTORE_ENCRYPTED_FILE": str(archive),
        "AYAHOS_RESTORE_SHA256": hashlib.sha256(archive.read_bytes()).hexdigest() if checksum else "0" * 64,
        "AYAHOS_RESTORE_AGE_IDENTITY_FILE": str(identity),
        "AYAHOS_DISPOSABLE_RESTORE": "1" if authorized else "0",
        "EXPECT_EMPTY": "1" if empty else "0",
        "FAIL_CMD": fail,
        "FAKE_RLS_COUNT": str(rls_count),
        "FAKE_CONVERSATION_RLS_COUNT": str(conversation_rls_count),
        "FAKE_SCHEMA_VERSIONS": str(migrations),
    }
    return subprocess.run([sys.executable, str(SCRIPT)], check=False, env=env,
                          capture_output=True, text=True, timeout=20)


def test_successful_disposable_restore(tmp_path):
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "isolated_restore_verified" in result.stdout


def test_refuses_remote_target(tmp_path):
    assert _run(tmp_path, url="postgresql://postgres@db.example.com/ayahos_restore_test01").returncode != 0


def test_refuses_production_name(tmp_path):
    assert _run(tmp_path, url="postgresql://postgres@localhost/postgres").returncode != 0


def test_refuses_without_disposable_acknowledgement(tmp_path):
    assert _run(tmp_path, authorized=False).returncode != 0


def test_refuses_nonempty_target(tmp_path):
    assert _run(tmp_path, empty=False).returncode != 0


def test_refuses_bad_archive_hash(tmp_path):
    assert _run(tmp_path, checksum=False).returncode != 0


def test_refuses_failed_decryption(tmp_path):
    assert _run(tmp_path, fail="age").returncode != 0


def test_refuses_failed_pg_restore(tmp_path):
    assert _run(tmp_path, fail="pg_restore").returncode != 0


def test_inherited_libpq_overrides_cannot_redirect_restore(monkeypatch, tmp_path):
    monkeypatch.setenv("PGHOSTADDR", "203.0.113.7")
    monkeypatch.setenv("PGSERVICE", "attacker")
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "isolated_restore_verified" in result.stdout


def test_refuses_restored_schema_without_protected_tables(tmp_path):
    result = _run(tmp_path, rls_count=5)
    assert result.returncode != 0
    assert "isolated_restore_verified" not in result.stdout


def test_refuses_missing_schema_migrations(tmp_path):
    result = _run(tmp_path, migrations=0)
    assert result.returncode != 0
    assert "isolated_restore_verified" not in result.stdout


def test_schema_24_restore_requires_customer_table_rls(tmp_path):
    result = _run(tmp_path, migrations=24, conversation_rls_count=1)
    assert result.returncode != 0
    assert "isolated_restore_verified" not in result.stdout


def test_schema_24_restore_checks_all_eight_critical_rls_tables(tmp_path):
    result = _run(tmp_path, migrations=24, conversation_rls_count=2)
    assert result.returncode == 0, result.stderr
    assert '"critical_rls_tables": 8' in result.stdout


def test_schema_22_rehearsal_does_not_require_unapplied_customer_tables(tmp_path):
    result = _run(tmp_path, migrations=22, conversation_rls_count=0)
    assert result.returncode == 0, result.stderr
    assert '"critical_rls_tables": 6' in result.stdout
