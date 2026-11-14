# Recovering AyahOS from the private R2 ciphertext

Status, 2026-10-23: **rehearsal runner added; production archive has NOT yet been restored to PostgreSQL**.

## Grounded preflight

- Live encrypted object exists in the private Cloudflare R2 bucket
  `ayahos-db-backups-private`, last observed key
  `ayahos-xgomhbuzawoqnwlzvavx-20261023T044912Z-a4bfe609.dump.age`.
- Recorded SHA-256 from its originating authenticated backup readback:
  `f3f8f221fc76cd6cedbf3f6cb38dbdde23e90e6e19f6be5fe81e0f0b01602d66`.
- Do **not** interpret object existence as proof the age identity can decrypt it, a
  PostgreSQL restore succeeds, or historical rows can be recovered.
- Do **not** restore to Render, a shared production DB, or an existing local DB.
- The connected Oracle SentinelX agent runs as a restricted service user and
  does not currently have a local PostgreSQL server, private age identity,
  R2 secret, or access to the Node 001 worktree. This host is not a verified
  restoration target. Preserve its least-privilege security settings.

## Trusted, operator-provisioned prerequisites

1. Choose an isolated host with PostgreSQL **17** (server and client),
   compatible pgvector extension, and sufficient free disk.
2. Provision an **empty local** PostgreSQL database whose name begins with
   `ayahos_restore_` (for example `ayahos_restore_rehearsal01`).
   Confirm it is on localhost and cannot reach production accidentally.
3. Retrieve the age private identity **out of separate, independently recoverable
   escrow** into a mode-0600 owner-only file. Never put it in this repository,
   GitHub Actions artifacts, Render env, chat, shell history, or R2.
4. Configure an authenticated, least-privilege `rclone` R2 remote through a
   restricted config. Ensure only the private bucket is accessible.
5. Inject the following required environment variables via your trusted local
   secret manager (values below are illustrations, **not** credentials):

   ```text
   AYAHOS_DISPOSABLE_RESTORE=1
   AYAHOS_RESTORE_PROJECT_REF=xgomhbuzawoqnwlzvavx
   AYAHOS_RESTORE_RCLONE_REMOTE=<private-rclone-name>:ayahos-db-backups-private
   AYAHOS_RESTORE_ARCHIVE_NAME=ayahos-xgomhbuzawoqnwlzvavx-20261023T044912Z-a4bfe609.dump.age
   AYAHOS_RESTORE_SHA256=f3f8f221fc76cd6cedbf3f6cb38dbdde23e90e6e19f6be5fe81e0f0b01602d66
   AYAHOS_RESTORE_AGE_IDENTITY_FILE=<owner-only-path-to-escrowed-identity>
   AYAHOS_RESTORE_DATABASE_URL=postgresql://<disposable-user>@localhost/ayahos_restore_rehearsal01
   ```

6. On the isolated host run `python3 scripts/db/rehearse_recovery.py`.
   The command downloads **ciphertext only** to a private temporary directory,
   re-verifies the expected SHA-256, calls the existing fail-closed
   `restore_verify.py`, and deletes temporary ciphertext afterward. A
   nonempty or nonlocal target, a broken identity file, an unexpected project,
   a corrupted R2 object or a failed pg_restore causes failure. The code
   refuses to claim full disaster recovery solely from these structural gates.
   Never run this in an automatic job with production DB credentials.

## Acceptance evidence, beyond tool's success

Record UTC start/end, original ciphertext hash and byte count, isolated
database identity (sanitized), migration versions, core RLS tables, PostgreSQL
and pgvector version, number of restored rows per application table, source
snapshot row counts (collected at backup time, not from a later changing
production DB), source/restore sample checksums without customer payloads,
and independently recovered key provenance. Verify the most important
Spine request/event history, Ruby jobs, and any RAG entries.

A successful runner output proves **one isolated structural restore**, not
that all Supabase Auth/Storage/roles/secrets, recent writes or historical
customer data were preserved. Full RPO/RTO and data correctness require
separate comparison evidence and an independently operated restore.

## Scheduling and release gates

Do not activate a daily backup schedule, automatic retention, destructive
migrations, or close Issue #365 merely because the runner tests pass.
After actual recovery evidence, approve backup cadence and cost limits,
prepare backup-freshness notifications, and run a guarded release process
with CI and authenticated chat persistence tests.

No private key or user data should be copied into CI logs, R2 public URLs
or ChatGPT.
