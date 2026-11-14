# Linux-first migration: P0 source and runtime baseline

**Observed:** 2026-10-24 UTC. **Scope:** read-only checks only. **Status:** evidence inventory, **not** HQ release certification or authorization to switch traffic. **Source:** current GitHub API/CLI and unauthenticated, read-only HTTP probes. The authoritative monorepo and deployment configuration remain unchanged.

## Release authority and exact source revisions

The current production source authority is `fuaadabdullah/AyahOS_Dual_Lineage` on `main` at `dbf9fbde52a11bbc069e19bdeca2658d8dcc1147`. The original monorepo is **private**. The independent HQ platform release process is still a candidate, not an established replacement.

| Repository | Observed main SHA | Visibility | Authority |
| --- | --- | --- | --- |
| `fuaadabdullah/AyahOS_Dual_Lineage` | `dbf9fbde52a11bbc069e19bdeca2658d8dcc1147` | Private | Current canonical source |
| `ayahos-hq/ayahos-site` | `a1f9461881aa4068d39a91ce4adbdf1dd73069cc` | Private | HQ candidate |
| `ayahos-hq/ayahos-core` | `28162d26b3471e8f3866577bcbf7c155f4a211c6` | Private | HQ candidate |
| `ayahos-hq/ayahos-admin` | `223a3b6ce6783405a4822a3cddbbbe66cc3164c2` | Private | HQ candidate |
| `ayahos-hq/ayahos-platform` | `696f04f8359acdf4dc600acca543f3b5af5a2119` | Public | HQ candidate, release definitions |
| `ayahos-hq/ayahos-workloads` | `e4de3aab568fc817816a4bd9e58eaeb0296f7a53` | Private | HQ candidate |

**Manifest reconciliation update:** platform PR [#31](https://github.com/ayahos-hq/ayahos-platform/pull/31) **merged at 2026-10-24T02:05:07Z** as `696f04f8359acdf4dc600acca543f3b5af5a2119`. The manifest now pins Workloads SHA `e4de3aab568fc817816a4bd9e58eaeb0296f7a53`, confirmed by a read of the updated Linux-native checkout. Artifact digests remain null and cross-repo, database-restore, live-smoke and rollback acceptance remain pending. A newer source SHA is never a passing release gate.

## Read-only runtime observations

| Surface | Exact probe / evidence | Result | What it does **not** establish |
| --- | --- | --- | --- |
| Primary Cloudflare Pages site | `GET https://ayahos.pages.dev/api/build` | HTTP 200; `build_sha=dbf9fbde52a11bbc069e19bdeca2658d8dcc1147`; `source_branch=main` | Chat/SSE/auth, provider fallback, external DNS or rollback health |
| Vercel rollback site | `GET https://ayahos.vercel.app/api/build` | HTTP 200; older `build_sha=49994571435b9a1e89232c38f37689a934a75f91` | Rollback parity or traffic-switch rehearsal |
| Render API | Unauthenticated `GET https://goblin-dual-lineage-api.onrender.com/v1/runtime/status` | HTTP 401, as expected for an auth-protected endpoint | Actual deployed API SHA, authenticated API health and request behavior |
| Existing Cloudflare Octopus bridge | `GET https://ayahos-octopus-github-bridge.fuaadabdullah.workers.dev/healthz` | HTTP 200 | Full trigger wiring, worker test logs or HQ project verification |
| Monorepo Octopus status | GitHub commit status `octopus/verify` for `dbf9fbde...` | `success` at `2026-10-23T23:18:17Z`; [task reference](https://ayahos.octopus.app/app#/Spaces-1/tasks/ServerTasks-1683) | Independent inspection of all required lane logs or any HQ release |
| Registry gateway | Unauthenticated `GET https://ayahos-registry-gateway.vercel.app/api/registry` | HTTP 405 (POST-only API) | Authenticated Google Agent Registry discovery or authorization to enable routing |
| `ayahos.dev` custom hostname | DNS lookup from connected Windows workstation | Host not resolved during this observation | Registration/DNS ownership; not proof Pages is down |

The existing bridge is documented as connected to the monorepo project, **not** HQ. Its live configuration was not independently inspected in this pass. Do not repoint it to HQ. The gateway authentication and Google WIF configuration were reviewed separately; this P0 inventory did not read or export credentials.

## Relevant concurrent change requests (observed open)

- HQ platform [#17](https://github.com/ayahos-hq/ayahos-platform/pull/17): isolated Google Agent Registry gateway; updated branch `dc76d1f085a738ebf18b27aa35de55e5cdb8d9c3`, still draft.
- HQ platform [#28](https://github.com/ayahos-hq/ayahos-platform/pull/28): Octopus manifest verifier invocation; draft.
- HQ platform [#30](https://github.com/ayahos-hq/ayahos-platform/pull/30): Gemini/Cline review worker preparation; draft.
- Monorepo [#401](https://github.com/fuaadabdullah/AyahOS_Dual_Lineage/pull/401): read-only Agent Registry discovery evidence; draft and its merge checks were pending at observation.

Newer PRs or deployment checks may change. Re-fetch their head SHAs and statuses before any write, merge, Octopus release or cutover.

## Linux-native baseline (separate read-only test)

A new non-root `pgrun` working copy of the public `ayahos-hq/ayahos-platform` `main` was cloned to `/home/pgrun/src/ayahos/ayahos-platform` on Ubuntu 24.04 WSL2's native ext4 filesystem, **not** `/mnt/c`. It resolved to `696f04f8359acdf4dc600acca543f3b5af5a2119` with a clean working tree. Running `PYTHONDONTWRITEBYTECODE=1 python3 scripts/run-hq-offline-tests.py` completed successfully with 33 script tests and seven runner/Octopus tests. This is **verified local Linux source testing only**, not a cloud Octopus run or cross-repository release. Ubuntu currently has Python 3.12.3 and Ruby 3.2.3; `node` is absent in the Linux environment, so Node tests are not claimed there. The older Windows working copies were not modified by this clone.

## Infrastructure classification and unresolved evidence

- **Canonical runtime boundaries:** Cloudflare Pages customer-facing surface, protected Render API and deterministic policy, Vercel rollback site, Octopus verification and separate inference infrastructure. These are **observed/documented roles**, not a blanket live-acceptance claim.
- **HQ release chain:** independent Octopus project, exact-five-SHA source assembly, artifact digests, cross-repo contracts, PostgreSQL 16/pgvector, rollback and signed evidence remain **unverified or pending**. Never infer them from the monorepo `octopus/verify` success.
- **Render deployments:** the current deployed API revision could not be independently read through the unauthenticated public status route. Confirm by an authorized read-only deployment view; do not assume parity with `main`.
- **DNS and rollback:** Cloudflare Pages origin and Vercel fallback respond, but the intended public custom domain and tested failover mechanism have not been established here.
- **Secrets/cost:** no production secret values, token exports, billing changes or new cloud resources were used for this inventory. Workspace-scoped Render data and Octopus authenticated task logs require separate authorized evidence.

## Non-regression boundary

Until the [Linux release gates](./linux-release-gates.md) are satisfied, keep production DNS, Render/Vercel/Cloudflare settings, database state, Octopus monorepo bridge, policy authority and enabled feature flags exactly as they are. Separate read-only inventories from implementation work, and never treat a passing source test as production acceptance.

**Next evidence required:** (1) authorized Render deployment SHA, (2) underlying Octopus task logs on the recorded source SHA, (3) production chat/auth/SSE baseline without leaking credentials, (4) billing and rollback ownership, and (5) independent HQ worker/gate proof. Unknown is an explicit blocked state, not a success.