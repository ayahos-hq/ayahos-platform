"""Emit safe DB project identity hints without exposing connection credentials.

The output is an operator-only startup diagnostic, not proof that a service
successfully connected to the database or that a project is authoritative.
"""
from __future__ import annotations

import json
import os
import re
from urllib.parse import unquote, urlsplit

_PROJECT_REF = re.compile(r"^[a-z]{20}$")
_POOLER_HOST = re.compile(r"^[a-z0-9.-]+\.pooler\.supabase\.com$")


def _identity(url: str) -> dict[str, str]:
    if not url:
        return {"kind": "missing"}
    try:
        parts = urlsplit(url)
        hostname = (parts.hostname or "").lower()
        user = unquote(parts.username or "")
        if parts.scheme not in {"postgres", "postgresql"} or not hostname:
            return {"kind": "unrecognized"}
        if hostname.startswith("db.") and hostname.endswith(".supabase.co"):
            ref = hostname[3:-len(".supabase.co")]
            if _PROJECT_REF.fullmatch(ref):
                return {"kind": "supabase", "project_ref": ref}
        if _POOLER_HOST.fullmatch(hostname) and user.startswith("postgres."):
            ref = user[len("postgres."):]
            if _PROJECT_REF.fullmatch(ref):
                return {"kind": "supabase", "project_ref": ref}
        if hostname in {"localhost", "127.0.0.1", "::1"}:
            return {"kind": "local"}
        return {"kind": "other"}
    except (ValueError, TypeError):
        return {"kind": "unrecognized"}


def summary(env: dict[str, str]) -> dict[str, object]:
    canonical = env.get("DATABASE_URL", "")
    spine = env.get("DUAL_LINEAGE_SPINE_DATABASE_URL", "").strip() or canonical
    rag = env.get("DUAL_LINEAGE_RAG_DATABASE_URL", "").strip() or canonical
    targets = {"database": _identity(canonical), "spine": _identity(spine), "rag": _identity(rag)}
    refs = [item["project_ref"] for item in targets.values() if item.get("kind") == "supabase"]
    configured_mode = env.get("DUAL_LINEAGE_DATABASE_MODE", "local").strip().lower()
    return {
        "event": "db.target_identity",
        "storage_mode": configured_mode if configured_mode in {"local", "postgres"} else "invalid",
        "targets": targets,
        "consistent_supabase_refs": len(set(refs)) <= 1 if len(refs) == 3 else None,
        "note": "parsed configuration only; connection and writer identity unverified",
    }


if __name__ == "__main__":
    print(json.dumps(summary(dict(os.environ)), sort_keys=True))
