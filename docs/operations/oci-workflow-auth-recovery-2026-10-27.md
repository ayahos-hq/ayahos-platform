# OCI workflow P0: authentication failure and bounded restart containment

**Observed 2026-10-27 UTC. Status: source mitigation verified locally; live authority remains blocked.**
Tracking: [#424](https://github.com/fuaadabdullah/AyahOS_Dual_Lineage/issues/424).

## Root cause and blast radius

On OCI `goblin-control` (instance suffix `bamtfzca`), both `goblin-workflow-worker.service` and `goblin-workflow-scheduler.service` exceeded **52,000** restarts each. `journalctl` shows their PostgreSQL connection exits with `FATAL: password authentication failed` for the legacy runtime account, and systemd restarts the processes every five seconds. An authorized, **presence-only** check against `/etc/goblin/workflow.env` classifies their `DATABASE_URL` as **Render**, not Supabase. Do not log or copy its plaintext. The suspended legacy Render API does not establish a usable workflow DB, and the old Render evidence PostgreSQL expires 2026-10-27 at 06:58 UTC.

The live Supabase project `xgomhbuzawoqnwlzvavx` is the chosen app data authority, but **no equivalent Ruby workflow database connection has been verified**. Do not substitute connection strings, reset a database, or fabricate a working credential. User jobs could be queued; never discard or replay them while recovering the worker.

## Safe mitigation committed in both systemd templates

- `Restart=on-failure`, **600-second minimum restart delay**, and **four starts per hour** via `StartLimitIntervalSec=3600`, `StartLimitBurst=4`. A persistent invalid password ultimately stops attempts rather than generating another tens of thousands of restarts. On success the long-lived worker and scheduler keep running. A deliberate operator restart is needed after a start limit is hit.
- Preserve existing `EnvironmentFile`, `PGSSLMODE=require`, executable paths, sandboxing and permissions. Do not dilute `NoNewPrivileges` or write database credentials to Git, logs, command lines, or issue comments.
- Unit-template test: `python3 apps/api/tests/test_oracle_workflow_restart_policy.py`. This is a **source-only** test; live remediation requires deploying approved units and repairing secret authority.

## Operator deployment gates — do not run automatically

1. Preserve current `systemctl cat`, `systemctl show` and historical journals, then identify existing queued jobs and consumer dependencies. Locate **approved** runtime database ownership and secure secret-store delivery path, compare with the canonical Supabase tables and migration status. Verify any Render-only rows against its separately restore-tested private R2 snapshot.
2. Reissue a **least-privilege** workflow role and password through authorized Supabase/database administration only after correct privileges and TLS are checked. No production DDL or bulk restore based on an unreviewed guess. Install the validated URL through the existing root-controlled `/etc/goblin/workflow.env` secret file with mode 0600; do **not** use `systemctl show-environment`, unredacted env dumps, or CLI arguments.
3. After test credentials work under `PGSSLMODE=require`, install reviewed worker/scheduler units at their canonical systemd paths, run `systemd-analyze verify`, `systemctl daemon-reload`, `systemctl reset-failed` for the two named units, and restart **only** these approved services. Keep the other OCI model services alive. Exact operations require an authorized maintenance window and rollback.
4. Read only sanitized state and error class: `systemctl is-active`, unit restarts, read-only queue health, and database access under the intended role. Expect **zero additional auth failures** for 30 minutes, stable restart counts, and queue processing with durable idempotency. Failed auth or lost data is a hard HOLD; roll back the units and secret file from controlled backup.
5. Node 001's local backend can return HTTP 200 while `/health` reports `registration.ok=false` due to the upstream Render API returning HTTP 503. Source fix PR #423 was merged; backoff is not upstream recovery. Restore a real authoritative control API and prove registration, authenticated inference, SSE, Undermind and Shared Spine before claiming end-to-end success.
6. Only after the Octopus exact-SHA release, runtime and recovery gates pass may a production cutover or Render deletion be considered.

**Current change boundary:** No live Render, Supabase, OCI unit files, systemd daemons, database credentials, or Fly machines are modified by this commit.
