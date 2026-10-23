# AyahOS Supabase project and test databases

Status as of 2026-10-20: **schema verified-local against the migration runner; no data; not wired to any
service.** Nothing here proves a service uses this project.

## Persistent project

| Field | Value |
|---|---|
| Name | `ayahos-dual-lineage` |
| Project ref | `nqbclsoqtdvkrojwhrvw` |
| Organization | GoblinOS (free plan) |
| Region | `us-east-1` |
| Created | 2026-10-20 |
| Data | none |

Migrations `001` to `018` were applied through the Supabase connector in four ordered batches, with a
ledger row per version in `dual_lineage_schema_migrations`. The database password was not available, so
`python -m dual_lineage.db migrate` was not used against it.

### Verification

The same migrations were run with `python -m dual_lineage.db migrate` on a local PostgreSQL 16 that has
the `anon` and `authenticated` roles. Content hashes of the following catalogs were then compared with
the Supabase project, and every one matched:

| Catalog | Objects | Hash (md5) |
|---|---|---|
| columns | 168 | `732b76f2cf5f6d788f49a21f8558d45d` |
| constraints | 48 | `518d70df58b4452072b4bb2015b13bb1` |
| indexes | 37 | `96c25a23cb6215ad5f6add249f47b9fe` |
| RLS flags | 17 | `d2ce825b909431513b22f736d7a79bec` |
| policies | 16 | `e11125d6836e82a883f3d3dad4eed675` |
| migration ledger | 18 | `68daa81587a24067c6eb2cd3cddfec67` |

Supabase security advisors reported two items, both caused by the repo's own migrations:

- INFO `rls_enabled_no_policy` on `dual_lineage_release_evidence`: migration 018 enables RLS without a
  deny policy. Client roles are still denied, because RLS with no policy denies everything.
- WARN `extension_in_public` for `vector`: migration 017 creates it without a schema. Moving it needs a
  search-path decision for the RAG service first.

### Not done

- Render `DATABASE_URL` is unchanged. Cutting over needs a decision about the canonical store.
- `supabase-copper-island` (`xgomhbuzawoqnwlzvavx`), named as canonical in the other infrastructure
  docs, is not readable from the connector used here (permission denied). No data was moved from it.
- No connection string or password is recorded in this repository.

## Test and training databases

Some suites drop the `public` schema, so test databases must be **disposable** and never the persistent
project. The plan is one Supabase branch per CI or training run, deleted afterwards.

Intended wiring, not in effect yet:

- Octopus project variable `TEST_DATABASE_URL` (sensitive): the connection string of that run's branch.
- Octopus project variable `CI_TEST_DATABASE_IS_DISPOSABLE` = `1`: set only together with a disposable
  branch URL.

Current behavior:

- `scripts/ci/octopus_verify.sh` sets `TEST_DATABASE_URL` to its local `ayahos_ci` database in
  `setup_pgvector()`. That overrides a project variable of the same name, so the Octopus lanes never
  reach a Supabase branch. Wiring the branch path means changing that script; that is a decision,
  not made here.
- `scripts/ci/verify.sh` refuses a non-local database unless `CI_TEST_DATABASE_IS_DISPOSABLE` is `1`.
  Its guard lives in `scripts/ci/test_database_guard.sh`. For a database marked disposable, the `api`
  and `worker` gates empty the `public` schema before they migrate it.
- Plain local URLs (`localhost`, `127.0.0.1`, `[::1]`, `db`, with no query string and no host list)
  are always allowed. Anything else counts as remote, including a `host=` or `hostaddr=` query
  parameter, which libpq would use to override the host.

Unverified: branch creation bills hourly and may not be available on the free plan; no branch has been
created. `verify.sh` reads Octopus variables with `get_octopusvariable`, and that helper has not been
confirmed inside the Octopus execution container used here. If it is missing, set the two values as
environment variables on the step instead.
