"""Configured DB identity must win over inherited libpq connection overrides."""
import importlib.util
from pathlib import Path

MODULE = Path(__file__).resolve().parents[2] / "scripts" / "db" / "postgres_env.py"
spec = importlib.util.spec_from_file_location("postgres_env", MODULE)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_untrusted_pg_overrides_are_removed() -> None:
    ambient = {
        "PGHOSTADDR": "203.0.113.7", "PGSERVICE": "hijacked",
        "PGOPTIONS": "-c search_path=unsafe", "PGDATABASE": "wrongdb",
        "PGSSLROOTCERT": "/tmp/fake-ca", "PATH": "/bin",
    }
    connection = {"PGHOST": "db.expected.supabase.co", "PGDATABASE": "postgres", "PGSSLMODE": "verify-full"}
    result = module.isolated_postgres_environment(connection, ambient=ambient)
    assert result == {"PATH": "/bin", **connection}


def test_trusted_ca_opt_in_preserved() -> None:
    ambient = {"AYAHOS_PGSSLROOTCERT": "/secure/trust.crt", "PGSSLROOTCERT": "/tmp/attacker.crt"}
    result = module.isolated_postgres_environment({"PGHOST": "localhost"}, ambient=ambient)
    assert result["PGSSLROOTCERT"] == "/secure/trust.crt"


def test_no_connection_override_with_empty_connection() -> None:
    assert module.isolated_postgres_environment({}, ambient={"PGHOSTADDR": "1.2.3.4"}) == {}
