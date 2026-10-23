# AyahOS database restore rehearsal

The canonical recovery runner is `scripts/db/rehearse_recovery.py`. It is a
schema and RLS gate, not a claim that production data has been recovered.

The operator must provision an empty PostgreSQL 17 target on `localhost`,
retrieve the age identity from independent escrow into an owner-only file, and
provide authenticated private-object-storage access through the trusted local
environment. The identity, database URL, provider credentials, and R2
credentials must never be committed, passed as command arguments, or printed.

Required environment variables:

```text
AYAHOS_DISPOSABLE_RESTORE=1
AYAHOS_RESTORE_PROJECT_REF=<20-character project ref>
AYAHOS_RESTORE_RCLONE_REMOTE=<private-rclone-remote>:<bucket>/<prefix>
AYAHOS_RESTORE_ARCHIVE_NAME=ayahos-<project>-<UTC timestamp>-<short hash>.dump.age
AYAHOS_RESTORE_SHA256=<64 lowercase hex characters>
AYAHOS_RESTORE_AGE_IDENTITY_FILE=<owner-only local path>
AYAHOS_RESTORE_DATABASE_URL=postgresql://<user>:<password>@localhost/ayahos_restore_<name>
```

Run from the repository root:

```text
python scripts/db/rehearse_recovery.py
```

The runner downloads only to a mode-0700 temporary directory, verifies the
encrypted checksum, streams age decryption into `pg_restore`, refuses a
non-local or non-empty target, and checks contiguous migrations plus required
RLS tables. It deletes the temporary ciphertext before exit. A successful
result still requires separate source-versus-restored row-count comparison and
operator sign-off before backup scheduling or recovery alerts are activated.
