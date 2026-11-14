# OCI Ruby workflow database authority — October 27, 2026

**Evidence-based recovery, not a production activation declaration.**

## Verified diagnosis

- Oracle VM `goblin-control` (OCI ID suffix `bamtfzca`) runs `goblin-workflow-worker.service` and `goblin-workflow-scheduler.service` with `EnvironmentFile=/etc/goblin/workflow.env`. That file holds a **Render**-class PostgreSQL URL. The runtime repeatedly logs `FATAL: password authentication failed` for a legacy user and has accumulated more than 52,000 restarts per unit.
- A second root-protected `/etc/goblin/workflow-worker.env` exists, but its `DATABASE_URL` is **not a parseable postgresql:// URL**; do not switch the services to that file blindly.
- Canonical AyahOS Supabase project `xgomhbuzawoqnwlzvavx` is healthy, PostgreSQL 17.11. It holds 1,568 `ruby_workflow_jobs` (1,371 dead, 197 succeeded), 1,389 audit rows and 19 inbox messages. No jobs are in a running/queued state at observation.
- **Independent recovery proof for all three workflow tables:** a fresh October 26 private-R2 encrypted Render PostgreSQL 18 dump was decrypted and successfully restored into a network-isolated, disposable PG18 container. Counts and ordered full-row MD5 aggregate hashes exactly matched the Supabase three tables (jobs `abf40dd96994995dd736190d9fe657cf`, audit `78c1713a21c88fe4a2299a16834127d6`, inbox `3a296a83ed435f7f3225ac65793a76c5`). This proves those tables in that snapshot are recoverable, **not** a full Supabase Auth, Storage or live Postgres 17 restore.
- `goblin_runtime_20261002` does not exist in the inspected Supabase project. The existing `goblin_runtime` login role has **no explicit privileges** to SELECT, INSERT or UPDATE workflow tables and cannot insert audit events. There are no role-specific RLS policies for it.

## Prepared operator-only, least-privilege recovery

- `scripts/db/provision_workflow_db_role.sql`: additive and idempotent; creates dedicated `ayahos_workflow_20261027` as **NOLOGIN**, no elevated roles or RLS bypass, then grants only workflow job SELECT/INSERT/UPDATE, audit SELECT/INSERT, sequence usage, schema usage and corresponding RLS policies. Does not grant public client access, mutate rows, modify existing roles, or embed a credential. It is **not an automatic application migration**.
- `scripts/db/verify_workflow_db_role_isolated.sql`: isolated-restore-only transactional grant test; verifies the role sees 1,568 jobs and 1,389 audit rows, exercises INSERT into audit and zero-row UPDATE, and ROLLBACK leaves historical data unchanged.
- The SQL script was applied **twice without error** to the disposable restored PG18 instance. The isolated role test passed, including authenticated-role policy and audit sequence. No live Supabase DDL was applied: the connected write was blocked by the platform safety gate. Do not substitute another tool to bypass that gate.

## Approval and deployment gates

1. Obtain approved Supabase DB administration channel, confirm canonical target and current vault/secret custody. Review this SQL and execute only through an authorized DBA path after a current isolated restore and an operator-approved maintenance window.
2. Generate a new 256-bit role secret inside the trusted OCI server, not in GitHub/chat, and set the role's password using a one-way `SCRAM-SHA-256` verifier. A root-only candidate password file has been staged at `/etc/goblin/.ayahos-workflow-20261027.secret` (mode 0600), **not activated** or copied to any logs. Its recovery escrow is not yet verified; replace or retire the file if a different credential flow is chosen. Do not record the verifier or plaintext in a commit.
3. With the role enabled through an approved database-admin change, select the **exact** IPv4 Supabase *session-pooler* endpoint from the project's **Connect** dialog. On these OCI micro VMs, public IPv6 lacks an upstream route; the direct IPv6 host is not viable. For pooler, use the role-qualified username (`ayahos_workflow_20261027.xgomhbuzawoqnwlzvavx`), port 5432, database `postgres`, and TLS. Do not guess the pooler hostname, weaken TLS, or pay for an IPv4 add-on.
4. Test a **read-only** connection as the dedicated role on OCI and verify both grants and the workflow queue's expected schema under `PGSSLMODE=require` or stronger certificate verification. Save current unit and environment files before any change.
5. Change only the two named systemd services to use the securely provisioned workflow URL, with the separately proposed bounded restart limit from PR #425, then `systemctl daemon-reload`, controlled restart and health verification. Observe stable counts and durable queue/audit updates using a uniquely identified approved synthetic job. No requeue of 1,371 dead historical jobs without distinct approval.
6. Run Octopus exact-SHA verification, independent live auth/inference/telemetry gates and an explicit rollback drill before any Render retirement.

## Constraints and blockers

Production DDL and role activation were **not authorized by the available tool safety gate**. The root-only secret remains unactivated. The other PR #425's authoritative Octopus check currently reports failure. Neither this role-provisioning source package nor its offline tests make the production worker healthy. Render evidence Postgres expires on 2026-10-27 06:58 UTC; a restore-tested October 26 archive already exists in private R2.
