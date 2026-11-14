# Live Ruby RAG verification

This is the shortest safe path to live evidence. It never prints or stores a runtime key,
database URL, or DashScope key.

## One command

Inject the approved values through the shell or CI secret store, then run:

```powershell
$env:LIVE_API_URL = "https://goblin-dual-lineage-api.onrender.com"
$env:LIVE_RUNTIME_API_KEY = (Get-Secret -Name DualLineageRuntimeKey -AsPlainText)
$env:LIVE_EXPECTED_SHA = "<deployed-commit-sha>"
$env:LIVE_RAG_SMOKE_OUTPUT = "artifacts/live-rag-smoke.json"
ruby scripts/live_rag_smoke.rb
```

The command fails closed if either required variable is missing or the URL is invalid. The
production defaults require PostgreSQL, DashScope-backed embeddings, and pgvector. Do not set
the `LIVE_RAG_REQUIRE_*` variables to `0` for production evidence.

## Evidence produced

The JSON artifact records, without credentials:

- served SHA and RAG/runtime configuration;
- database type and selection source (`explicit_rag_url` or `shared_database_url`);
- embedded and indexed chunk counts;
- ingest, search, cognition, trace, and cleanup latency;
- retrieval mode (`vector` proves the remote query embedder authenticated; `lexical` is fallback);
- grounded cognition citation and post-delete non-retrievability.

## Acceptance

Accept the live path only when the artifact has `status: "passed"`, the expected SHA matches,
the database is PostgreSQL, embeddings and pgvector are enabled, cognition cites the probe, and
cleanup succeeds. A missing credential, HTTP 401/403, embedding failure, non-vector trace under
strict defaults, or SQLite selection is a stop—not a partial live pass.

The pgvector-unavailable path is covered locally by the Ruby RAG suite: an indexed-query database
error demotes retrieval to the JSON full scan and records `rag.pgvector_unavailable`. A relaxed
live run may observe a deployed full-scan fallback, but it must be labeled separately from strict
production evidence.
