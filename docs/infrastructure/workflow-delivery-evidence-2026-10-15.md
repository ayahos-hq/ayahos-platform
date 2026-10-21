# Ruby workflow delivery evidence, 2026-10-15

Scope: the Ruby queue-to-Python inbox delivery (`/v1/workflow/inbox`) and the PostgreSQL-backed
worker. Baseline `main` was `a34b5b5`; the operator web and public site both served that SHA
during this check.

## Summary

| Claim | Status |
| --- | --- |
| Ruby PostgreSQL queue (leases, retries, dead letter, requeue, scoped claim) | verified-local; now runs in CircleCI `ruby` with zero skips |
| Ruby queue -> Python inbox delivery, API in postgres mode, receipt stored in PostgreSQL | verified-local; now runs in CircleCI `ruby` (`workflow_delivery_test.rb`) |
| `external_event` receipts in postgres mode | bug found and fixed by migration 015 (they failed the insert before) |
| Authenticated delivery to the live API | unverified: no live runtime key available to this check |
| Live PostgreSQL-backed worker | unverified: no Ruby worker is deployed and no live database URL was available |

## Local verification (verified-local)

Environment: PostgreSQL 16.15, Python 3.11.17, Ruby 3.3.6. Every database was created empty and
migrated with `python -m dual_lineage.db migrate`.

On baseline `a34b5b5`, before any change:

- `test/postgres_queue_test.rb` with `TEST_DATABASE_URL`: 5 runs, 21 assertions, 0 failures, 0 skips.
- `test/python_api_contract_test.rb` with `RUN_PYTHON_API_CONTRACT=1`: 4 errors. The API exits at
  import with `DUAL_LINEAGE_RAG_URL is required for the ruby backend`, which has been true since
  `3f1f465` removed the Python RAG backend. Only GitHub Actions ran this test, and every Actions
  run currently ends in `startup_failure`, so the failure was not visible.
- `scripts/live_workflow_smoke.rb` against a local API in postgres mode with the matching key:
  exit 0, `"status":"passed"`. The receipt row was stored as `provider_failure | completed |
  audit_only` and carried the job's observability envelope.
- The same smoke with a key the API does not hold: exit 1. The job dead-letters on its first
  attempt with `HTTP 403: invalid dual-lineage runtime key`. This matches the exit-1 failures of
  `production-workflow-smoke` in the 2026-10-14 refresh (jobs 313 and 329). That attribution is an
  inference: the CircleCI logs for those jobs were not read in this check.
- A direct insert of an `external_event` receipt failed
  `dual_lineage_workflow_inbox_messages_message_type_check`. Migration 011's CHECK predates that
  message type, so in postgres mode (the deployed mode) every signed-webhook delivery returned
  500. Ruby retried each one until it dead-lettered.

With this change applied:

- Ruby worker suite with `TEST_DATABASE_URL`, `RUN_PYTHON_API_CONTRACT=1` and
  `RUBY_WORKER_REQUIRE_INTEGRATION=1`: 76 runs, 538 assertions, 0 failures, 0 skips. The run used a
  fresh worktree, `vendor/bundle` gem paths and a uv-managed Python 3.11 venv, the same setup as
  the CircleCI job.
- The same run without a database gives 9 failures (each "RUBY_WORKER_REQUIRE_INTEGRATION is set
  but ...") and no skips.
- `workflow_delivery_test.rb` checks the following:
  - The PostgreSQL queue delivers to the inbox, and the receipt is stored with the sent
    `spine_event_id`.
  - After an API restart, a redelivery is `duplicate` and still only one row exists.
  - `workflow_state_change`, `provider_failure` and `external_event` are all stored.
  - A rejected key dead-letters with no receipt.

  The `external_event` case failed before migration 015, with HTTP 500 and the job left pending
  for retry.
- API suite against PostgreSQL migrated to 15: 571 passed, 0 skipped. Ruff and mypy pass.
  `scripts/release_gate.py` passes all seven checks, and the Ruby client matches the Python
  contract.
- `live_workflow_smoke.rb` with `LIVE_WORKFLOW_DATABASE_URL` against the local API: exit 0 with
  `"queue":"postgres","inbox_receipt":"postgres"`. An older due job planted in the same queue
  stayed `pending` with 0 attempts, so the smoke claims only its own job. With a wrong key it
  exits 1.

## Live probes (keyless, read-only)

These were run on 2026-10-15 with no credentials and GET requests only:

| UTC | Request | Result |
| --- | --- | --- |
| 00:28:10Z | `GET https://goblin-dual-lineage-api.onrender.com/health` | 200 `{"status":"ok","service":"ayahos-control-ruby","core":"healthy"}` |
| 00:28:11Z | `GET https://goblin-dual-lineage-api.onrender.com/v1/runtime/status` | 401 `dual-lineage runtime key is required` (fails closed) |
| 00:28:12Z | `GET https://goblin-dual-lineage-web-live.onrender.com/api/build` | 200 `build_sha` `a34b5b550bb36aa74a633dfe06ea3a61d4b7b626` |
| 00:28:12Z | `GET https://ayahos.vercel.app/api/build` | 200 `build_sha` `a34b5b550bb36aa74a633dfe06ea3a61d4b7b626`, branch `main` |

The API's own SHA and the inbox both need the runtime key, so neither was observed. An earlier
scripted attempt timed out client-side after 60 s before it reported anything. That attempt would
also have sent a keyless inbox POST, and whether the POST was sent is unknown. A keyless POST is
rejected before the handler runs. The attempt is not used as evidence.

## What closes the live rows

1. Synchronize the deployed `DUAL_LINEAGE_RUNTIME_API_KEY` with CircleCI's `LIVE_RUNTIME_API_KEY`.
   Step 1 of the clearing procedure in
   [`release-handoff-2026-10-14-phase6-refresh.md`](../release-handoff-2026-10-14-phase6-refresh.md)
   covers this.
2. Let the deploy apply migration 015. `start-dual-lineage.sh` migrates before the API starts.
3. Run `production-release`. `production-workflow-smoke` must print `"status":"passed"`. That
   result proves authenticated queue-to-inbox delivery against the live API.
4. To prove the live PostgreSQL path as well, provide the deployment's database URL to the smoke
   as `LIVE_WORKFLOW_DATABASE_URL`. The smoke must then also report `"queue":"postgres"` and
   `"inbox_receipt":"postgres"`. Putting a production database credential in CircleCI is an
   owner decision. Without it, the live PostgreSQL row stays unverified.
