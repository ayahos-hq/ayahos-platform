"""Safe DB identity diagnostics must never print credentials or raw hosts."""
from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE = Path(__file__).resolve().parents[2] / "scripts" / "db" / "runtime_targets.py"
spec = importlib.util.spec_from_file_location("runtime_targets", MODULE)
assert spec is not None and spec.loader is not None
targets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(targets)

REF = "xgomhbuzawoqnwlzvavx"
REF2 = "nqbclsoqtdvkrojwhrvw"


def test_pooler_identity_redacts_password() -> None:
    source = f"postgresql://postgres.{REF}:u7s!!@aws-0-us-east-1.pooler.supabase.com:5432/postgres"
    result = targets.summary({"DATABASE_URL": source})
    assert result["targets"]["database"] == {"kind": "supabase", "project_ref": REF}
    assert "u7s!!" not in str(result)
    assert ".pooler.supabase.com" not in str(result)
    assert result["consistent_supabase_refs"] is True


def test_cross_project_divergence_visible_without_credentials() -> None:
    source = f"postgresql://postgres.{REF}@aws-0-us-east-1.pooler.supabase.com/postgres"
    other = f"postgresql://postgres.{REF2}:password@aws-0-us-east-1.pooler.supabase.com/postgres"
    result = targets.summary({"DATABASE_URL": source, "DUAL_LINEAGE_RAG_DATABASE_URL": other})
    assert result["targets"]["rag"]["project_ref"] == REF2
    assert result["consistent_supabase_refs"] is False
    assert "password" not in str(result)


def test_direct_connection_recognized() -> None:
    result = targets._identity(f"postgresql://postgres:pw@db.{REF}.supabase.co/postgres")
    assert result == {"kind": "supabase", "project_ref": REF}


def test_non_supabase_host_redacted() -> None:
    result = targets.summary({"DATABASE_URL": "postgresql://user:secret@private.internal:5432/private_db"})
    assert result["targets"]["database"] == {"kind": "other"}
    assert "private.internal" not in str(result)
    assert "private_db" not in str(result)


def test_invalid_urls_do_not_echo_input() -> None:
    assert targets._identity("postgresql://secret@[broken") == {"kind": "unrecognized"}


def test_missing_env_does_not_invent_project() -> None:
    result = targets.summary({})
    assert result["targets"]["database"] == {"kind": "missing"}
    assert result["consistent_supabase_refs"] is None


def test_reports_mode_without_echoing_an_untrusted_value() -> None:
    assert targets.summary({"DUAL_LINEAGE_DATABASE_MODE": "local"})["storage_mode"] == "local"
    assert targets.summary({"DUAL_LINEAGE_DATABASE_MODE": "postgres"})["storage_mode"] == "postgres"
    assert targets.summary({"DUAL_LINEAGE_DATABASE_MODE": "secret-text"})["storage_mode"] == "invalid"
