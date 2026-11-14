# AyahOS: Octopus-only encrypted database backup operations

Status (2026-10-23): **workflow committed, Octopus runbook not activated until
its worker, sensitive variables and real restore gate are verified.**
GitHub Actions is retired for both database backups and the status relay.
GitHub remains the source repository; Octopus handles verification and
operational runbooks, and the existing Cloudflare Octopus bridge handles checks.

## Architecture and privilege separation

- `.octopus/deployment_process.ocl` remains the **eight-step secrets-free CI
  verification process**. Do not add production database URLs to these steps,
  branch-triggered verification, Octopus live release smoke, or the Cloudflare
  bridge. GitHub PR code is untrusted.
- `.octopus/runbooks/encrypted-database-backup.ocl` defines the independent
  **Encrypted database backup** runbook. It uses the Git resource from a
  protected/default `main` branch and the dedicated `ayahos-backup` worker
  pool, **not** the small hosted-ubuntu CI worker and not the Render API.
- `scripts/ci/octopus_db_backup.sh` maps Octopus runbook-scoped sensitive
  variables to the existing `scripts/db/backup_postgres.py` streaming,
  authenticated-readback runner. It uses an in-memory rclone S3 remote, with
  no credentials written to a config file, in argv, or a plaintext archive.
- Disable branch/runbook producer execution on unreviewed commits with
  production variable access. Prefer a **separate backup Octopus project** if
  the existing CI project cannot scope secrets exclusively to the backup
  runbook. Never grant write rights to any CI or PR execution step.
- Octopus runbooks on an existing Config-as-Code project may require the
  operator's one-way **Store Runbooks in Git** migration. Confirm this state
  in the Octopus UI before relying on the OCL file to be discovered. Runbook
  OCL is the proposed source, **not evidence of an installed Octopus runbook**.

## Operator activation (owner/Octopus project admin)

1. In `https://ayahos.octopus.app`, identify the already authorized
   AyahOS project and Space. Confirm this runbook belongs to a project with
   access to only the intended source and that `main` is protected. Enable
   Config-as-Code runbooks using the documented Octopus UI migration, if
   needed. Do not discard or silently replace unrelated existing runbooks.
2. Create and verify the `ayahos-backup` worker pool on an approved,
   isolated Node 001 or Oracle machine, **separate from the Octopus CI pool**.
   The worker must have PostgreSQL 17 client `pg_dump`, `age`,
   `rclone`, Python 3.11+, a restricted machine account and read-only
   validated Supabase connectivity. The hosted verification worker may be
   insufficient and should not receive DB credentials.
3. Create the following Octopus variables in the project, scoped to the
   **Encrypted database backup runbook only** (not deployment process,
   CI steps or other runbooks). Enter sensitive values in the **Octopus
   sensitive-variable store**, never `.octopus/variables.ocl` or GitHub:

   | Octopus variable | Value requirements |
   | --- | --- |
   | `AyahOS.Backup.DatabaseUrl` | Sensitive, restricted backup role for canonical Supabase project; TLS verified |
   | `AyahOS.Backup.ProjectRef` | Nonsecret: `xgomhbuzawoqnwlzvavx` |
   | `AyahOS.Backup.AgeRecipient` | Public encryption recipient; **not the private identity** |
   | `AyahOS.Backup.CAFile` | Path to the operator-verified Supabase CA bundle on backup worker |
   | `AyahOS.Backup.R2AccessKeyId` | Sensitive, bucket-scoped R2 object access |
   | `AyahOS.Backup.R2SecretAccessKey` | Sensitive, bucket-scoped R2 object secret |
   | `AyahOS.Backup.RunApproved` | Remains unset until authorized operator starts a run; set `YES` only after approval |
   | `AyahOS.Backup.RestoreGatePassed` | Remains unset until real ciphertext was decrypted and restored successfully; then `YES` |

   Do **not** copy or try to read GitHub Actions secrets from the old
   `backup-production` environment. Provision/rotate independent
   scoped Octopus values using authorized provider dashboards.
4. Publish/verify the runbook configuration and inspect its execution
   environment, worker pool, source branch and target. Check runbook
   permissions: only trusted operator can change variables, publish,
   approve and run. Neither automated PR verification nor a webhook
   should launch it.
5. First perform a real off-host encrypted archive restore to an isolated
   PostgreSQL 17 database, using `scripts/db/rehearse_recovery.py` and
   independently escrowed age identity; confirm row counts, RLS and recovery
   metrics. The prior R2 object exists, but it has **not** been verified
   as restorable. Until this gate passes, the backup runbook intentionally
   refuses to run.
6. When the above is proven, approve a **single manual Octopus runbook
   execution** from `main`. Confirm the job uses the dedicated worker,
   prints only sanitized `uploaded_verified` metadata (no DB password,
   age private key or R2 credential), and records an authenticated
   SHA-256 readback from private R2. Confirm zero plaintext dumps.
7. Only then consider **an Octopus scheduled runbook trigger** at an
   explicit daily UTC time within free-plan task/storage quotas. Set up
   failure alerts and the existing read-only freshness watch. Never
   schedule the prior GitHub workflow again or enable overlapping cron.

## Verification and rollback

- GitHub `.github/workflows/encrypted-database-backup.yml` and
  `.github/workflows/octopus-status-relay.yml` are removed. Prior
  historical GitHub Actions run failures remain in GitHub history; removal
  does not erase history or secrets. Revoke **retired** GitHub environment
  access after Octopus migration verification, not before.
- Verify Octopus step task logs prove the exact default-branch commit,
  selected worker, actual `pg_dump 17`, encryption, R2 object and readback.
  An OCL file, local unit test or empty bucket is insufficient.
- If Octopus has not been provisioned or is unavailable, leave the
  runbook closed and keep the existing **verified encrypted R2 archive**
  untouched. The read-only freshness alert will report staleness;
  do not quietly fall back to untested GitHub Actions or modify
  production PostgreSQL.
- This runbook backs up the application's `public` schema only;
  Supabase Auth, Storage objects and global role configuration require
  separate recovery plans. Do not call this whole-project disaster recovery.

References: `docs/operations/database-backups-runbook.md`,
`docs/operations/database-restore-rehearsal-2026-10-23.md`, Issue #365.
