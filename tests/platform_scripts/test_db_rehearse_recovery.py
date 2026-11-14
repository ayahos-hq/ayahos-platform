"""Credential-free tests for private off-site restore rehearsal orchestration."""
from __future__ import annotations

import hashlib
import sys
import types
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "db"
sys.path.insert(0, str(SCRIPT))
import rehearse_recovery as rehearsal

REF = "xgomhbuzawoqnwlzvavx"
NAME = f"ayahos-{REF}-20261023T044912Z-a4bfe609.dump.age"
CONTENTS = b"encrypted-backup-only-test-bytes"


@pytest.fixture(autouse=True)
def no_real_restore(monkeypatch):
    def mock_verify(archive, expected_checksum, identity, target_url):
        assert Path(archive).read_bytes() == CONTENTS
        assert expected_checksum == hashlib.sha256(CONTENTS).hexdigest()
        assert Path(identity).name == "identity.txt"
        assert target_url == "postgresql://restore@localhost/ayahos_restore_rehearsal01"
        return {
            "status": "isolated_restore_verified",
            "schema_migrations": 22, "critical_rls_tables": 6,
            "encrypted_sha256": expected_checksum, "target": "local_disposable",
        }

    monkeypatch.setattr(rehearsal, "verify_restore", mock_verify)


def _env(tmp_path):
    key = tmp_path / "identity.txt"
    key.write_text("FAKE TEST IDENTITY")
    key.chmod(0o600)
    return {
        "AYAHOS_DISPOSABLE_RESTORE": "1",
        "AYAHOS_RESTORE_PROJECT_REF": REF,
        "AYAHOS_RESTORE_RCLONE_REMOTE": "private-r2:ayahos-db-backups-private",
        "AYAHOS_RESTORE_ARCHIVE_NAME": NAME,
        "AYAHOS_RESTORE_SHA256": hashlib.sha256(CONTENTS).hexdigest(),
        "AYAHOS_RESTORE_DATABASE_URL": (
            "postgresql://restore@localhost/ayahos_restore_rehearsal01"
        ),
        "AYAHOS_RESTORE_AGE_IDENTITY_FILE": str(key),
    }


def _download(command, **kwargs):
    assert command[:2] == ["rclone", "copyto"]
    assert command[2] == f"private-r2:ayahos-db-backups-private/{NAME}"
    Path(command[3]).write_bytes(CONTENTS)
    return types.SimpleNamespace(returncode=0)


def test_verified_ciphertext_then_isolated_restore(monkeypatch, tmp_path):
    monkeypatch.setattr(rehearsal.subprocess, "run", _download)
    result = rehearsal.rehearse(_env(tmp_path))
    assert result["status"] == "isolated_restore_verified"
    assert result["archive"] == NAME
    assert result["schema_migrations"] == 22
    assert result["disaster_recovery_complete"] is False


@pytest.mark.parametrize("name,value", [
    ("AYAHOS_DISPOSABLE_RESTORE", "false"),
    ("AYAHOS_RESTORE_PROJECT_REF", "otherprojectabcdefghijkl"),
    ("AYAHOS_RESTORE_ARCHIVE_NAME", "../escape.age"),
    ("AYAHOS_RESTORE_RCLONE_REMOTE", "local:/tmp/archives"),
    ("AYAHOS_RESTORE_RCLONE_REMOTE", "private-r2:bucket/../evil"),
    ("AYAHOS_RESTORE_RCLONE_REMOTE", "../some/path"),
    ("AYAHOS_RESTORE_SHA256", "not a digest"),
    ("AYAHOS_RESTORE_DATABASE_URL", "postgresql://postgres@example.com/postgres"),
])
def test_refuses_unsafe_inputs_before_download(monkeypatch, tmp_path, name, value):
    calls = []
    monkeypatch.setattr(
        rehearsal.subprocess, "run", lambda *a, **k: calls.append(True)
    )
    settings = _env(tmp_path)
    settings[name] = value
    with pytest.raises(rehearsal.RehearsalError):
        rehearsal.rehearse(settings)
    assert calls == []


def test_corrupted_ciphertext_never_reaches_decryption(monkeypatch, tmp_path):
    def corrupted(command, **kwargs):
        Path(command[3]).write_bytes(b"corrupted")
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(rehearsal.subprocess, "run", corrupted)
    with pytest.raises(rehearsal.RehearsalError, match="checksum"):
        rehearsal.rehearse(_env(tmp_path))


def test_download_failure_does_not_restore(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rehearsal.subprocess, "run",
        lambda *a, **k: types.SimpleNamespace(returncode=1),
    )
    with pytest.raises(rehearsal.RehearsalError, match="download failed"):
        rehearsal.rehearse(_env(tmp_path))


def test_private_key_symlink_is_refused_before_transfer(monkeypatch, tmp_path):
    settings = _env(tmp_path)
    actual = tmp_path / "actual.key"
    actual.write_text("FAKE TEST IDENTITY")
    link = tmp_path / "symlink.key"
    link.symlink_to(actual)
    settings["AYAHOS_RESTORE_AGE_IDENTITY_FILE"] = str(link)
    monkeypatch.setattr(
        rehearsal.subprocess, "run", lambda *a, **k: pytest.fail("network call"),
    )
    with pytest.raises(rehearsal.RehearsalError):
        rehearsal.rehearse(settings)


def test_object_download_does_not_inherit_db_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "postgresql://private:password@db.example/db")
    monkeypatch.setenv("PGPASSWORD", "must-not-pass-to-rclone")
    monkeypatch.setenv("OPENAI_API_KEY", "do-not-forward-provider-token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "do-not-forward-other-token")
    monkeypatch.setenv("RCLONE_CONFIG", "/tmp/fake-private-rclone-config")


    def _safe_transfer(command, **kwargs):
        child_env = kwargs["env"]
        assert "DATABASE_URL" not in child_env
        assert "PGPASSWORD" not in child_env
        assert "OPENAI_API_KEY" not in child_env
        assert "ANTHROPIC_API_KEY" not in child_env
        assert child_env["RCLONE_CONFIG"] == "/tmp/fake-private-rclone-config"

        assert "AYAHOS_RESTORE_DATABASE_URL" not in child_env
        return _download(command, **kwargs)

    monkeypatch.setattr(rehearsal.subprocess, "run", _safe_transfer)
    result = rehearsal.rehearse(_env(tmp_path))
    assert result["status"] == "isolated_restore_verified"
