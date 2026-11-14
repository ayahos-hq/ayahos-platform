#!/usr/bin/env bash
# Source before launching API/Ruby. Schema writes belong to a separate release step.
ayahos_prepare_schema() {
  local mode="${DUAL_LINEAGE_DATABASE_MODE:-local}"
  case "$mode" in
    local) return 0 ;;
    postgres)
      if [[ -z "${DATABASE_URL:-}" ]]; then
        echo '{"event":"db.schema_missing_connection","message":"DATABASE_URL is required for postgres mode"}' >&2
        return 1
      fi
      if [[ "${DUAL_LINEAGE_SCHEMA_AUTO_MIGRATE:-false}" == "true" ]]; then
        if [[ "${DUAL_LINEAGE_ENV:-production}" != "development" ]]; then
          echo '{"event":"db.schema_auto_migrate_forbidden","message":"Production schema migration belongs in a guarded release step"}' >&2
          return 1
        fi
        python -m dual_lineage.db migrate
        return $?
      fi
      # Read-only verification. No credentials on command line.
      python -m dual_lineage.db check
      return $?
      ;;
    *) echo '{"event":"db.invalid_storage_mode"}' >&2; return 1 ;;
  esac
}
