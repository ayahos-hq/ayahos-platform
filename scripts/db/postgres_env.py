"""Keep child libpq clients away from ambient PostgreSQL overrides."""

from __future__ import annotations

import os
from collections.abc import Mapping


def isolated_postgres_environment(
    connection: Mapping[str, str], *, ambient: Mapping[str, str] | None = None
) -> dict[str, str]:
    source = os.environ if ambient is None else ambient
    clean = {key: value for key, value in source.items() if not key.startswith("PG")}
    clean.update(connection)
    if source.get("AYAHOS_PGSSLROOTCERT"):
        clean["PGSSLROOTCERT"] = source["AYAHOS_PGSSLROOTCERT"]
    return clean
