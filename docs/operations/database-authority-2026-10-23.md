# AyahOS database authority and recovery baseline (2026-10-23 UTC)

Status: **live read-only inventory verified; cutover and disaster recovery unverified**.

## Production storage finding (verified 2026-10-23 02:35 UTC, later superseded)

The Render API deployment from commit `d5ec5f3ef77a58d901b3e4a7b75e977486762c75` emitted a sanitized startup `db.target_identity` diagnostic reporting:

- `storage_mode: local`
- `targets.database.kind: missing`
- `targets.spine.kind: missing`
- `targets.rag.kind: missing`

Thus the **currently observed Render service is not connected to PostgreSQL**. A successful HTTP `/health` check is not proof of durable persistence. Treat request history and locally held control/operational state as ephemeral until a later live, authenticated run shows `spine_storage=postgres` with healthy matching schema and actual request persistence. The accessible Supabase project holds historical data, but **is not the verified production writer** at this observation.

The target should remain `local` until: (1) the intended DB source is chosen and backed up with a tested isolated restore, (2) a least-privilege connection secret is configured and validated, (3) the startup migration is safely gated, and (4) authenticated live end-to-end checks prove reads/writes survive redeployment. Changing the deployment setting alone does not establish any of these. Do not delete the historical project or silently dual-write.


## Later runtime and database evidence (2026-10-23 06:15 UTC)

Render API logs now report `storage_mode: postgres` and parsed Supabase project ref `xgomhbuzawoqnwlzvavx` for the database, Spine and RAG. This only verifies configuration parsing, **not the live writer identity**. The earlier local-mode observation below is historical, not current.

The connected incumbent was queried **read-only**: PostgreSQL 17.11, schema ledger **1..22**, and no `ayahos_conversations` or `ayahos_messages` tables. PR #342 proposes migrations 023/024 and remains unmerged. Cloudflare site/API health endpoints returned HTTP 200, not authenticated persistence proof. The private R2 bucket contains the backup-named object `ayahos-xgomhbuzawoqnwlzvavx-20261023T044912Z-a4bfe609.dump.age` (1,284,921 bytes, last modified 04:49:15 UTC, verified by private object metadata). Independent ciphertext decryption and an isolated restore have **not** been completed; existence is not proof of recoverability. All 14 focused offline restore-verifier regressions passed. These tests do **not** substitute for a recoverable encrypted source backup and isolated Postgres restore, so production DDL remains blocked.

## Authority, observed rather than assumed

- Production repository remains `fuaadabdullah/AyahOS_Dual_Lineage`. The five `ayahos-hq` repositories are provisional extractions and must not independently execute production migrations.
- Render service `goblin-dual-lineage-api` (`srv-dasd3ajbc2fs73eos5jg`) deploys from that monorepo's `main`. At inventory time its latest listed deploy (`a7ef41fe1ec6a680bc734a5d54890fb13972d3a3`) was `live`; an HTTP health response does not itself identify the database it uses.
- Connected Supabase project `supabase-copper-island` (`xgomhbuzawoqnwlzvavx`) reported `ACTIVE_HEALTHY`, PostgreSQL 17.6, region us-east-1. It has real historical Shared Spine, workflow and metrics data. **This makes it the incumbent store for preservation, not proof that all currently running writers target it.**
- A separate project `ayahos-dual-lineage` (`nqbclsoqtdvkrojwhrvw`) is described in `docs/infrastructure/supabase-ayahos-project.md` as created on October 20 with an isolated migrated schema, no data and no app wiring *at that time*. It is not accessible through the Supabase connection used for this inventory. Treat it as an **unverified candidate**, not a replacement.
- Earlier inspection reported **21 ledger versions**. Later read-only verification found **22**, with customer-history 023/024 still pending. Reconcile these time-stamped observations; do not run schema-changing migrations or restart services solely to force them to match.

## Read-only baseline

| Probe | Readout |
| --- | --- |
| Connected database total size | 35 MB |
| Public application tables | 21 |
| Public tables with RLS enabled | 21 |
| Shared Spine events (estimated) | 6,924 active; 4,089 archived |
| Ruby workflow jobs (estimated) | 1,568 |
| Schema ledger | 1..22 (06:13 UTC); customer-history migration 23/24 not applied |
| Security advisors | mutable function search path; `vector` in `public`; release evidence RLS with no policy (deny by default) |
| Performance advisors | 8 unused-index findings; not proof an index should be removed |
| Backup freshness and successful restore | **NOT VERIFIED** |
| Render `DATABASE_URL` target / schema read-through | **NOT VERIFIED** (never print connection strings) |
| Retention scheduler actual last success | **NOT VERIFIED** |
| Retrieval/pgvector end-to-end | **NOT VERIFIED** |

The rows from Supabase's table listing are approximations; use SQL `count(*)` only when exact counts are needed. An unused index on an empty RAG table is not evidence of waste. Do not blindly drop HNSW indexes.

## Ownership contract

1. **One canonical write target**: preserve `supabase-copper-island` until runtime connection metadata and a restorable backup are verified. Do not dual-write to both projects.
2. **One migration authority**: `apps/api/src/dual_lineage/db/migrations/` is the schema source while the monorepo deploys. The future `ayahos-core` takes schema ownership *only after* an evidence-backed cutover. `ayahos-platform` orchestrates, never forks schema definitions.
3. **Domain repositories, single durable database**: private Shared Spine, worker jobs/inbox, metrics/evidence and Ruby RAG data remain logically separate, but share PostgreSQL transactions and governed access. Frontend/Admin do not receive a privileged connection string.
4. **Release rules**: snapshot/backup and restore proof precede destructive changes. Gate migrations on exact database identity, compatibility and post-migration health; an unexpected ledger gap blocks rollout. Migrations must be idempotent and concurrency-safe.
5. **No replacement data plane by default**: Firebase, D1 and Redis are not authoritative stores. SQLite remains a local fallback.

## Stage gates (STOP unless satisfied)

### P0: authoritative writer identity

- Confirm, by redacted server-side telemetry, the DB **host/project reference** used by Render API, Ruby worker and RAG. Never log username, password or complete URL.
- Cross-check the live API's authenticated schema version and served commit; confirm if one of the two projects is used by any writer.
- Compare the source of the 06:13 UTC ledger-22 observation with actual Render writer identity before any further migration; a healthy deploy is not proof of persistence.
- Record one production DB owner and block any competing writer/cutover.

### P1: backups and security

- Prove at least one recent encrypted **off-site** PostgreSQL logical backup from the incumbent, and verify a restore into an isolated, disposable PostgreSQL instance; redact logs and keys.
- Confirm retention policies for backups and access/rotation for DB and encryption credentials. No plaintext dumps on unencrypted persistent storage.
- Apply security-advisor remediations only as additive versioned migrations, after tests and backup evidence. Moving `vector` requires checking Ruby RAG SQL, pgvector index dependencies and search paths.

### P2-P5: gradual deployment

- P2: serialize migration execution and verify schema checksum/history, use an Octopus-controlled pre-deploy gate, keep application startup read-only. Do not force a rollback by deleting migration ledger rows.
- P3: schedule bounded existing Python retention and report success time, counts, failures, growth, DB connections and pool saturation; keep free-tier jobs light.
- P4: verify real authorized RAG ingest/query, dimension/model identity, pgvector and lexical fallback.
- P5: tune only with sampled query plans and latency/connection evidence. Establish budget/scale alerts.

### Emergency recovery

Stop writers and maintain evidence of the served commit. Restore to a **new** isolated project/database, compare counts/schema, validate auth/Undermind/RAG and replay invariants, then deliberately switch connection secrets and perform controlled cutover. Do not restore over or truncate the incumbent as a first step. Keep the prior target read-only until confirmation.
