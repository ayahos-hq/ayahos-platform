"""Read-only encrypted backup freshness checks never imply restore success."""
from __future__ import annotations

import json
import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "db"))
import backup_freshness as freshness

REF = "xgomhbuzawoqnwlzvavx"


def _name(when, ref=REF):
    return f"ayahos-{ref}-{when.strftime('%Y%m%dT%H%M%SZ')}-a4bfe609.dump.age"


def _settings():
    return {
        "AYAHOS_BACKUP_PROJECT_REF": REF,
        "AYAHOS_BACKUP_RCLONE_REMOTE": "private-r2:ayahos-db-backups-private",
        "AYAHOS_BACKUP_MAX_AGE_HOURS": "30",
    }


def _fake_listing(items, code=0):
    return lambda *a, **kw: types.SimpleNamespace(
        returncode=code, stdout=json.dumps(items).encode(),
    )


def test_fresh_object_reports_age_but_not_restore(monkeypatch):
    now = datetime(2026, 10, 23, 6, 0, tzinfo=UTC)
    monkeypatch.setattr(freshness.subprocess, "run", _fake_listing([
        {"Path": _name(now - timedelta(hours=2)), "Size": 1284921, "IsDir": False}
    ]))
    result = freshness.check(_settings(), now=now)
    assert result["status"] == "fresh"
    assert result["age_hours"] == 2
    assert result["encrypted_bytes"] == 1284921
    assert result["restored"] is False and result["integrity_verified"] is False


def test_stale_object_fails(monkeypatch):
    now = datetime(2026, 10, 25, 6, 0, tzinfo=UTC)
    monkeypatch.setattr(freshness.subprocess, "run", _fake_listing([
        {"Path": _name(now - timedelta(days=2)), "Size": 50}
    ]))
    with pytest.raises(freshness.FreshnessError, match="stale"):
        freshness.check(_settings(), now=now)


def test_wrong_project_is_ignored(monkeypatch):
    now = datetime(2026, 10, 25, 6, 0, tzinfo=UTC)
    monkeypatch.setattr(freshness.subprocess, "run", _fake_listing([
        {"Path": _name(now, ref="a" * 20), "Size": 50}
    ]))
    with pytest.raises(freshness.FreshnessError, match="no qualifying"):
        freshness.check(_settings(), now=now)


def test_zero_byte_archive_is_not_fresh(monkeypatch):
    now = datetime(2026, 10, 25, 6, 0, tzinfo=UTC)
    monkeypatch.setattr(freshness.subprocess, "run", _fake_listing([
        {"Path": _name(now), "Size": 0}
    ]))
    with pytest.raises(freshness.FreshnessError):
        freshness.check(_settings(), now=now)


def test_future_timestamp_is_not_accepted(monkeypatch):
    now = datetime(2026, 10, 25, 6, 0, tzinfo=UTC)
    monkeypatch.setattr(freshness.subprocess, "run", _fake_listing([
        {"Path": _name(now + timedelta(hours=4)), "Size": 50}
    ]))
    with pytest.raises(freshness.FreshnessError):
        freshness.check(_settings(), now=now)


def test_failed_object_listing_fails_closed(monkeypatch):
    monkeypatch.setattr(freshness.subprocess, "run", _fake_listing([], code=5))
    with pytest.raises(freshness.FreshnessError, match="listing failed"):
        freshness.check(_settings())


def test_local_remote_rejected_before_network(monkeypatch):
    monkeypatch.setattr(freshness.subprocess, "run", lambda *a, **kw: pytest.fail("network"))
    settings = _settings()
    settings["AYAHOS_BACKUP_RCLONE_REMOTE"] = "local:/tmp/archives"
    with pytest.raises(freshness.FreshnessError):
        freshness.check(settings)


def test_invalid_freshness_threshold_rejected(monkeypatch):
    monkeypatch.setattr(freshness.subprocess, "run", lambda *a, **kw: pytest.fail("network"))
    settings = _settings()
    settings["AYAHOS_BACKUP_MAX_AGE_HOURS"] = "-100"
    with pytest.raises(freshness.FreshnessError):
        freshness.check(settings)


def test_backup_listing_does_not_receive_pg_credentials(monkeypatch):
    monkeypatch.setenv("PGPASSWORD", "not-for-object-store")
    monkeypatch.setenv("DATABASE_URL", "postgresql://private:secret@db.example/db")
    now = datetime(2026, 10, 23, 6, 0, tzinfo=UTC)

    def listing(command, **kwargs):
        assert "PGPASSWORD" not in kwargs["env"]
        assert "DATABASE_URL" not in kwargs["env"]
        return _fake_listing([{"Path": _name(now), "Size": 200}])(command)

    monkeypatch.setattr(freshness.subprocess, "run", listing)
    assert freshness.check(_settings(), now=now)["status"] == "fresh"
