"""Credential-free tests for external encrypted PostgreSQL backups."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "db" / "backup_postgres.py"
REF = "xgomhbuzawoqnwlzvavx"
SOURCE = f"postgresql://postgres.{REF}@aws-0-us-east-1.pooler.supabase.com:5432/postgres"
BACKUP_SOURCE = f"postgresql://ayahos_backup.{REF}@aws-0-us-east-1.pooler.supabase.com:5432/postgres"


def _run(tmp_path: Path, url: str, fail: str = "") -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    remote_dir = tmp_path / "offsite"
    remote_dir.mkdir(exist_ok=True)
    binaries = {
        "pg_dump": """#!/bin/sh
[ "${FAIL_CMD:-}" != pg_dump ] || exit 4
[ "${PGDATABASE:-}" = postgres ] || exit 40
[ "${PGSSLMODE:-}" = verify-full ] || exit 41
case "${PGUSER:-}" in
  postgres.xgomhbuzawoqnwlzvavx|ayahos_backup.xgomhbuzawoqnwlzvavx) ;;
  *) exit 42 ;;
esac
[ -z "${PGHOSTADDR:-}" ] || exit 44
[ -z "${PGSERVICE:-}" ] || exit 45
[ -z "${RCLONE_CONFIG_AYAHOS_R2_SECRET_ACCESS_KEY:-}" ] || exit 46
printf 'PGDMP fake pg archive'
""",
        "age": """#!/bin/sh
[ "${FAIL_CMD:-}" != age ] || exit 5
[ -z "${DATABASE_URL:-}" ] || exit 48
while [ "$1" != '-o' ]; do shift; done
shift
printf 'ENCRYPTED:' > "$1"
cat >> "$1"
""",
        "rclone": """#!/bin/sh
[ "${FAIL_CMD:-}" != rclone ] || exit 6
[ -z "${DATABASE_URL:-}" ] || exit 49
case "$1" in
 copyto) cp "$2" "$FAKE_OFFSITE/${3##*/}" ;;
 cat) cat "$FAKE_OFFSITE/${2##*/}" ;;
 *) exit 7 ;;
esac
""",
    }
    for name, script in binaries.items():
        executable = bin_dir / name
        executable.write_text(script)
        executable.chmod(0o700)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "DATABASE_URL": url,
        "AYAHOS_BACKUP_PROJECT_REF": REF,
        "RCLONE_CONFIG_AYAHOS_R2_SECRET_ACCESS_KEY": "FAKE_NONSECRET_TEST",
        "AYAHOS_BACKUP_AGE_RECIPIENT": "age1" + "q" * 55,
        "AYAHOS_BACKUP_RCLONE_REMOTE": "offsite:ayahos/pg",
        "FAKE_OFFSITE": str(remote_dir),
        "FAIL_CMD": fail,
        "TMPDIR": str(tmp_path),
    }
    return subprocess.run([sys.executable, str(SCRIPT)], check=False, env=env, capture_output=True, text=True, timeout=20)


def test_rejects_wrong_project(tmp_path: Path) -> None:
    result = _run(tmp_path, "postgresql://postgres.other@host.pooler.supabase.com/postgres")
    assert result.returncode != 0
    assert "project identity" in result.stderr
    assert not list((tmp_path / "offsite").iterdir())


def test_rejects_libpq_host_override(tmp_path: Path) -> None:
    assert _run(tmp_path, SOURCE + "?hostaddr=1.2.3.4").returncode != 0


def test_rejects_non_postgres_database(tmp_path: Path) -> None:
    assert _run(tmp_path, SOURCE.replace("/postgres", "/other")).returncode != 0


def test_rejects_transaction_pooler(tmp_path: Path) -> None:
    assert _run(tmp_path, SOURCE.replace(":5432", ":6543")).returncode != 0


def test_rejects_source_spoof(tmp_path: Path) -> None:
    assert _run(tmp_path, f"postgresql://postgres.{REF}@evilpooler.supabase.com/postgres").returncode != 0


def test_accepts_dedicated_backup_role(tmp_path: Path) -> None:
    result = _run(tmp_path, BACKUP_SOURCE)
    assert result.returncode == 0, result.stderr
    assert "uploaded_verified" in result.stdout


def test_rejects_unapproved_role(tmp_path: Path) -> None:
    source = SOURCE.replace("postgres.", "service_role.")
    assert _run(tmp_path, source).returncode != 0


def test_encrypts_and_verifies_remote_bytes(tmp_path: Path) -> None:
    result = _run(tmp_path, SOURCE)
    assert result.returncode == 0, result.stderr
    backups = list((tmp_path / "offsite").glob("*.age"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"ENCRYPTED:PGDMP fake pg archive"
    assert "uploaded_verified" in result.stdout
    assert not list(tmp_path.glob("ayahos-backup-*"))


def test_no_upload_when_dump_fails(tmp_path: Path) -> None:
    result = _run(tmp_path, SOURCE, fail="pg_dump")
    assert result.returncode != 0
    assert not list((tmp_path / "offsite").iterdir())


def test_no_upload_when_encryption_fails(tmp_path: Path) -> None:
    result = _run(tmp_path, SOURCE, fail="age")
    assert result.returncode != 0
    assert not list((tmp_path / "offsite").iterdir())


def test_no_false_success_when_remote_readback_fails(tmp_path: Path) -> None:
    result = _run(tmp_path, SOURCE, fail="rclone")
    assert result.returncode != 0
    assert "uploaded_verified" not in result.stdout


def test_password_never_printed_even_when_dump_fails(tmp_path: Path) -> None:
    result = _run(tmp_path, SOURCE.replace("@", ":SECRETPASSWORD@"), fail="pg_dump")
    assert result.returncode != 0
    assert "SECRETPASSWORD" not in result.stderr + result.stdout


def test_inherited_libpq_overrides_cannot_redirect_backup(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PGHOSTADDR", "203.0.113.7")
    monkeypatch.setenv("PGSERVICE", "attacker")
    result = _run(tmp_path, SOURCE)
    assert result.returncode == 0, result.stderr
    assert "uploaded_verified" in result.stdout
