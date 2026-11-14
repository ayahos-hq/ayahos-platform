# AyahOS encrypted PostgreSQL backups and recovery

Status (2026-10-23): **Octopus-only backup runbook implementation committed;
scheduled off-site backups and verified restores NOT ACTIVE**.

**Octopus is the sole backup orchestration authority.** The retired
GitHub Actions backup and status-relay workflows were removed in favor of
`.octopus/runbooks/encrypted-database-backup.ocl`, the existing Octopus CI
process, and the Cloudflare status bridge. For runbook variable setup,
dedicated worker-pool activation and rollout checks, see
[Octopus database backups](octopus-database-backups.md). This source-code
migration does not establish that the new Octopus runbook or credentials
have been provisioned on the remote Octopus project.

Supabase Free does not include customer-accessible managed daily backups; the project therefore requires an independent logical backup plus restore rehearsal. This is a **backup procedure**, not authorization to dump production data into Git, CI artifacts, logs, public object storage, or the ChatGPT workspace.

## Preflight gate

1. Confirm the canonical writer using the source identification checklist in `database-authority-2026-10-23.md`. The existing `supabase-copper-island` project is an incumbent with historic data; the newer candidate project is NOT a verified replacement.
2. Choose an authorized, secured **external execution host** (Node 001 or an Oracle VM, never the small Render API container). Confirm read-only backup credentials and `pg_dump` client major >= PostgreSQL 17.
3. Configure a genuine off-site destination owned by AyahOS, separate from both the source database and the execution host. Verify its access policy and storage cost are acceptable at $0. Never assume local filesystem or a second directory on the same host is off-site.
4. On the authorized operator host, supply `DATABASE_URL` as a restricted environment secret, together with the matching `AYAHOS_BACKUP_PROJECT_REF`. The backup runner parses the URL and sends isolated libpq parameters to `pg_dump`; credentials must not appear in argv, GitHub, PR logs, or rclone diagnostics. It rejects a mismatched Supabase project and inherited libpq connection overrides.
5. Generate an `age` encryption keypair; install only its **public recipient** on the backup machine. Retain the private identity encrypted and independently recoverable, away from production, backups and GitHub.


## Release and startup boundaries (as of October 23, 2026)

**Later observed mode (2026-10-23 06:15 UTC): `postgres` on the Render API.** Sanitized logs reference one Supabase project for database, Spine and RAG, but explicitly mark these as parsed configuration values, **not independently verified read/write persistence**. A live HTTP health check is not sufficient for durability proof. Do not change mode or target in response to older documentation.

Once an isolated restore succeeds and the intended Supabase project is approved, use a controlled, separately authorized release job to apply migrations with the secret only in the environment:

```bash
python -m dual_lineage.db migrate
python -m dual_lineage.db check
```

`DATABASE_URL` is read from the environment; **never put the full credential in process arguments, shell history, PRs or logs**. Running `migrate` is prohibited before a backup/restore rehearsal and exact source identity check. Confirm Python and Ruby services use the same authorized PostgreSQL target.

API startup in `postgres` mode now runs `python -m dual_lineage.db check` (read-only) rather than silently applying schema changes. A pending migration causes the startup to **fail closed**; it does not modify the database. Development-only migration-on-start can be enabled with `DUAL_LINEAGE_SCHEMA_AUTO_MIGRATE=true` and `DUAL_LINEAGE_ENV=development`. Production refuses that override.

After a verified backup restore, approved migrations and authenticated persistence smoke, reconcile existing Render `DATABASE_URL` / `DUAL_LINEAGE_DATABASE_MODE` with `render.yaml`. Change a secret or default only if the resulting writer identity and rollback plan are independently verified. Maintain the prior target untouched, keep retention-on-start off, and schedule a separately controlled bounded retention job **only after backups are proven**.

This stage is code and operations preparation, not evidence of a live PostgreSQL cutover.

## Safe operational sequence

- Execute `python scripts/db/backup_postgres.py` from the approved external host with `DATABASE_URL`, `AYAHOS_BACKUP_PROJECT_REF`, `AYAHOS_BACKUP_AGE_RECIPIENT`, and `AYAHOS_BACKUP_RCLONE_REMOTE` injected securely. It streams `pg_dump -Fc --schema=public` directly into age ciphertext; no plaintext dump file. The runner enforces `umask 077`, validates the Supabase connection identity and requires TLS `verify-full`. A separate export is needed for Supabase Auth, Storage objects and global role configuration.
- Stop on either dump or encryption failure. Upload the encrypted file to the independently configured object-store destination. Verify remote bytes by authenticated readback/checksum, then remove the temporary local ciphertext.
- Write only sanitized backup metadata: UTC timestamp, source project identifier, archive byte count, destination logical object key, transfer checksum, job status. Do not log SQL payload, archive content, DB URL, password, cloud key or private encryption identity.
- Retain daily and weekly recovery points within the measured free-tier limit, with a documented deletion policy. Never delete the last successfully restored copy.

The above is a specification; **it is not a configured cron job**. Keep production secrets out of the repository and require the destination to be operator approved before automating uploads.

## Restore rehearsal (separate controlled job)

1. Fetch a selected encrypted backup into a secure disposable test host and verify its encrypted checksum.
2. Decrypt to stdout using the separately stored age private identity; stream to `pg_restore` against a newly created, isolated local PostgreSQL 17 test database. Do not target the Supabase primary or another live project. A `pg_restore --list` check alone is not a restore rehearsal.
3. Use `python scripts/db/restore_verify.py` with a private age identity and only a specially named empty local disposable database (`AYAHOS_DISPOSABLE_RESTORE=1`). Preinstall PostgreSQL 17-compatible clients and the pgvector extension on the disposable host. The script refuses a nonempty/remote target and verifies encrypted checksum, PostgreSQL restore, contiguous migration history, and RLS on six critical Spine/workflow/RAG tables, plus the two customer-history tables for schema version 23 or later. **That success does not prove every row was restored.** Separately compare counts/schema/roles against source-side metadata, primary and foreign keys, RAG and Shared Spine replay invariants. Supabase-managed roles, auth/configuration and Storage API objects require separate exports and recovery steps: `pg_dump --schema=public` is not a whole Supabase project recovery.
4. Run read-only API acceptance against the disposable database with network/service boundaries intact. Record achieved restore time, success/failure and excluded assets, never raw user records.
5. Only after that proof may the operator schedule backup execution (daily) and restore rehearsals (weekly or monthly depending resources), with failures alerted.

## Disaster response

- Freeze application writers; preserve source database, identity and source commit.
- Restore into **new** isolated infrastructure. Never make a deletion or truncate the old project as a preliminary step.
- Compare schema and application invariants; exercise authenticated chat/control and rollback route.
- Change production connection destination only through approved deployment-secret management, after compatibility checks. Retain the original read-only until confirmed.

## Proposed owners

- `ayahos-core`: authoritative schema and database invariant tests.
- `ayahos-platform`: external backup job, scheduler, encrypted off-site destination, restore audit and operator-only status.
- `ayahos-admin`: read-only backup freshness / restore status. No one-click destructive restore.
- `ayahos-site` and `ayahos-workloads`: no privileged primary database credentials.

## Outstanding blockers

- Actual Render API + Ruby RAG database identity and schema read-through are not yet proved.
- The private Cloudflare R2 bucket (`ayahos-db-backups-private`) has no public domain and **contains** `ayahos-xgomhbuzawoqnwlzvavx-20261023T044912Z-a4bfe609.dump.age` (1,284,921 bytes, last modified 04:49:15 UTC). The object is confirmed via independent metadata; the originating backup workflow recorded a ciphertext checksum, but the ciphertext has **not** been independently decrypted or restored. Synthetic `age`/R2 transport and isolated schema-23/24 PostgreSQL tests passed, not a restore of user records. The connected control host lacks the separately escrowed age decryption identity and authorized R2 download profile.
- Supabase read-only inspection confirmed ledger **1..22** at 06:13 UTC; proposed customer-history migrations 023/024 are not applied and the conversation tables do not exist. Do not apply DDL without real backup/restore evidence and exact source identity.

## Opt-in encrypted backup freshness check

`python scripts/db/backup_freshness.py` is a **read-only**, credential-safe
health probe intended for a trusted operator or alerting service once daily
backups have been authorized. It requires
`AYAHOS_BACKUP_PROJECT_REF`, `AYAHOS_BACKUP_RCLONE_REMOTE`, and optionally
`AYAHOS_BACKUP_MAX_AGE_HOURS` (default **30 hours**, allowed 1–168). It
lists private rclone objects, only accepts archive filenames belonging to
the expected 20-character Supabase project and rejects zero-byte objects or
future-dated filenames. A failed listing or overdue archive exits nonzero and
prints a sanitized error. Neither this probe nor its success asserts that
an archive is intact, decryptable, or restorable; the result explicitly marks
`integrity_verified=false` and `restored=false`.

Do not activate a daily backup schedule, retention cron, or automated deletion
until an actual encrypted R2 archive has been restored on isolated PG17 with
the escrowed private identity and compared against source data. See
`database-restore-rehearsal-2026-10-23.md`. R2 bucket capacity and requests
must remain within the approved free-tier limits.
