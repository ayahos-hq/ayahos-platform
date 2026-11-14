#!/usr/bin/env bash
# Source from the API launch script. Only the co-located Ruby RAG process may
# use an automatically generated ephemeral bearer key. Remote RAG must be
# configured with a shared operator-managed key.
ayahos_bootstrap_rag_env() {
  export DUAL_LINEAGE_RAG_URL="${DUAL_LINEAGE_RAG_URL:-http://127.0.0.1:8102}"
  if [[ -n "${DUAL_LINEAGE_RAG_SERVICE_TOKEN:-}" ]]; then
    return 0
  fi
  case "$DUAL_LINEAGE_RAG_URL" in
    http://127.0.0.1:8102|http://localhost:8102)
      DUAL_LINEAGE_RAG_SERVICE_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" || return 1
      [[ -n "$DUAL_LINEAGE_RAG_SERVICE_TOKEN" ]] || return 1
      export DUAL_LINEAGE_RAG_SERVICE_TOKEN
      ;;
    *)
      echo '{"event":"rag.remote_token_missing"}' >&2
      return 1
      ;;
  esac
}
