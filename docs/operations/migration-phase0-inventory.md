# Migration Phase 0 — inventory and rollback baseline

**Issue:** [#243](https://github.com/fuaadabdullah/AyahOS_Dual_Lineage/issues/243) ·
**Runbook:** [`multi-repo-migration.md`](multi-repo-migration.md) ·
**Manifest:** [`migration/repositories.json`](../../migration/repositories.json)

- **Inventory SHA (source of truth):** `923f6bc51233a82732dab81e4b0a70eed62d9171` (`main`, merge of PR #292)
- **Captured:** 2026-10-22T05:26–05:28Z, from the checked-out tree at the inventory SHA plus the
  credential-free live checks and GitHub API reads recorded below.
- **Scope of this phase:** inventory, Phase 1 verification, and a rollback baseline. No code,
  DNS, secret, database, or hosting change was made. The monorepo
  `fuaadabdullah/AyahOS_Dual_Lineage` remains the canonical production source and was not
  deleted, renamed, or transferred.

Status words follow the repo vocabulary in `AGENTS.md` (`implemented`, `configured`,
`verified-local`, `verified-live`, `planned`, `unverified`).

---

## 1. Phase 1 verification — organization and destination repositories

Verified 2026-10-22T05:24–05:27Z with `gh` authenticated as the owner `fuaadabdullah` (repo IDs and creation timestamps corrected 2026-10-22 after a late-arriving API result exposed transcription errors in the first capture; re-verified against the live API in the correction PR)
(scopes `repo`, `read:org`, `workflow`) against the GitHub API. This is owner-level API
access; it supersedes the earlier connector-only checks, which could not see the org
repositories because the org-scoped app installation grant was a separate step.

### Organization

| Fact | Verified value |
| --- | --- |
| Login / display name | `ayahos-hq` / "AyahOS" |
| Org ID | `345776799` |
| Plan evidence | Created 2026-10-21T10:46:13Z; `total_private_repos: 5`, `owned_private_repos: 5`, `public_repos: 0` |
| Owner membership | `fuaadabdullah`: role `admin`, state `active` |
| Default repository permission | `read` |
| Two-factor requirement for members | **not enabled** (`two_factor_requirement_enabled: false`) |
| Member repository creation | `members_can_create_repositories: true`, incl. public repos (`members_can_create_public_repositories: true`) |
| Org profile | Description empty; no blog/location set |

### Repositories (all verified via `GET /repos/ayahos-hq/<name>` + git tree read)

| Repo | ID | Private | Default branch | Empty? | Tree entries (recursive) | Owner permissions | Created (UTC) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ayahos-site` | 1428241500 | yes (`visibility: private`) | `main` | no — 99 entries incl. `apps/`, `SOURCE-PROVENANCE.json`, `MIGRATION-GATES.md` | 99 | admin / push / pull | 2026-10-21T10:46:30Z |
| `ayahos-core` | 1428241578 | yes | `main` | no — incl. `apps/`, `docs/`, `SOURCE-PROVENANCE.json` | 331 | admin / push / pull | 2026-10-21T10:46:34Z |
| `ayahos-admin` | 1428241660 | yes | `main` | no — incl. `apps/`, `SOURCE-PROVENANCE.json`, `MIGRATION-GATES.md` | 78 | admin / push / pull | 2026-10-21T10:46:38Z |
| `ayahos-platform` | 1428241739 | yes | `main` | no — incl. `.octopus/`, `deploy/`, `scripts/`, `SOURCE-PROVENANCE.json` | 70 | admin / push / pull | 2026-10-21T10:46:42Z |
| `ayahos-workloads` | 1428241807 | yes | `main` | no — incl. `apps/`, `scripts/`, `SOURCE-PROVENANCE.json` | 63 | admin / push / pull | 2026-10-21T10:46:45Z |

Notes:

- The tree reads in this run correct two stale manifest lines: `ayahos-platform` and
  `ayahos-workloads` are no longer README-only placeholders; both now carry extracted
  content with provenance manifests. Content identity for those two was **not**
  re-hash-verified in this run — only presence and structure were verified.
- Phase 1's "create organization and five private repos" is therefore **verified**.
  Phase 1's "configure minimal permissions and org profile" is **not fully verified**:
  org-wide 2FA is not enforced, member repository-creation defaults remain permissive
  (including public repos), and the org profile is blank. Those are owner settings
  changes; they are recorded here as remaining work, not silently checked off.

---

## 2. Service inventory

Canonical deployment config: `render.yaml` (Render blueprint), `apps/site/wrangler.jsonc`
(Cloudflare Pages), `apps/site/vercel.json` (frozen fallback), `deploy/service-inventory.json`
(machine-readable service/evidence contract), `.octopus/` (release process).

| Surface | Source path | Host | Config | Live evidence |
| --- | --- | --- | --- | --- |
| Public site | `apps/site` (Next.js 16 static export + Pages Functions in `apps/site/functions/api/`) | Cloudflare Pages project `ayahos` | `apps/site/wrangler.jsonc` (`compatibility_date 2026-10-01`, flags `nodejs_compat`, `enable_request_signal`) | **verified-live (smoke)** 2026-10-22T05:26Z: `GET https://ayahos.pages.dev/api/build` → `build_sha 89e22cf0027f1fe3dd4131c153750dd6b38b2855`, `source_branch main`. Note: this is two merges behind the inventory SHA (`923f6bc`); the #292 deployment had not been observed live at capture time — treat the Pages deployment of `923f6bc` as **unverified**. |
| Public site fallback | `apps/site` (pinned build) | Vercel (`ayahos.vercel.app`) | `apps/site/vercel.json` (builds only from `main`/migration branch) | **verified-live (frozen, as designed)** 2026-10-22T05:26Z: `GET https://ayahos.vercel.app/api/build` → `build_sha 49994571435b9a1e89232c38f37689a934a75f91`. Intentionally behind `main`; rollback only. |
| API (authority: Overmind/Undermind/Spine/Action Gateway) | `apps/api` (FastAPI, Python ≥3.11) | Render web service `goblin-dual-lineage-api`, free plan, virginia, branch `main` | `render.yaml`; repo root `Dockerfile` | Configured. `/v1/runtime/status` requires the runtime key, so no credential-free identity read was taken in this run. Last live evidence per `docs/PROJECT_STATE.md` (2026-10-14→21 entries) remains limited: one successful public chat round-trip; full matrix **unverified**. |
| Control gateway (Ruby) | `apps/control-ruby` | Same Render API host (TLS gateway in front of API routes) | `render.yaml`, `apps/control-ruby/Gemfile` | **verified-live (smoke)** 2026-10-22T05:26Z: `GET https://goblin-dual-lineage-api.onrender.com/health` → HTTP 200, `{"status":"ok","service":"ayahos-control-ruby","core":"healthy"}`. Smoke only — not a functional E2E claim. |
| Operator web | `apps/web` (Next.js 16) | Render web service `goblin-dual-lineage-web-live`, free plan, virginia, branch `main` | `render.yaml`; `apps/web/next.config.mjs` (security headers) | Configured; identity path `/api/runtime` per `deploy/service-inventory.json`. Live SHA not freshly verified in this run (see PROJECT_STATE evidence). |
| RAG service (Ruby, Overmind + advisory Undermind corpora) | `apps/rag-ruby` | Co-located with API deployment (HTTP adapter from Python) | `apps/rag-ruby/Gemfile`; `DUAL_LINEAGE_RAG_*` env contract | Implemented; live retrieval **unverified** (PROJECT_STATE: live API rejected available credentials on 2026-10-14). |
| Ruby workflow worker | `apps/ruby_worker` | Not deployed as its own service (runs with API stack / operator submission) | `apps/ruby_worker/Gemfile`, `render.yaml` env | Implemented/configured; live delivery **unverified** per PROJECT_STATE. |
| Sandbox worker | `apps/sandbox_worker` (stdlib-only Python, gVisor, no network) | Dedicated VM (own host; not in `render.yaml`) | `deploy/sandbox/`, `docs/architecture/sandbox-worker.md` | Configured; live state **unverified** in this run. |
| Octopus → GitHub bridge | `deploy/octopus-github-bridge` (Cloudflare Worker) | Cloudflare Workers | `deploy/octopus-github-bridge/wrangler.jsonc` | Worker deployed and webhook live (2026-10-21). The `octopus/verify` commit status is **advisory** because the Worker's `GITHUB_STATUS_TOKEN` secret is still pending on the owner (see §5). |
| MCP bridges | `oracle_mcp_server.py`, `integrations/siliconflow-mcp/` | Render (`oracle-cloud-control-mcp`, `siliconflow-chatgpt-mcp`; not in the blueprint) | `oracle-mcp-requirements.txt`, `integrations/siliconflow-mcp/requirements.txt` | `active-bridge` per `deploy/service-inventory.json`; not re-verified in this run. |
| Compute nodes | `apps/api/src/dual_lineage/compute/` (registry/dispatch) | Node 001 (physical GPU box), future Oracle A1 | `.env.example` `DUAL_LINEAGE_COMPUTE_*`, `deploy/oracle/` | Configured; Node 001 GPU E2E **unverified** (last live observation 2026-09-27). |

Every extracted repository in §1 would need its own entry in this table re-verified at
its own exact SHA before any cutover; nothing in this phase moves a surface.

---

## 3. Dependency inventory (pinned at the inventory SHA)

| Ecosystem | Manifest(s) | Key pins at `923f6bc` |
| --- | --- | --- |
| pnpm workspace (root) | `package.json`, `pnpm-workspace.yaml`, `pnpm-lock.yaml` | `packageManager pnpm@9.15.9`; workspace members `apps/web`, `apps/site`, `packages/*` |
| Site | `apps/site/package.json` | next `16.3.3`, react/react-dom `19.2.8`, typescript `^5`, vitest `3.2.6`, wrangler `^4.151.2`, @playwright/test `1.64.1` (Tailwind/shadcn config removed by PR #292; its preflight defaults were moved into an explicit base reset in `globals.css`) |
| Web | `apps/web/package.json` | next `16.3.3`, react/react-dom `^19.2.6`, typescript `^5.9.3`, vitest `3.2.6` |
| Shared package | `packages/shared/package.json` | `@goblinos-dual-lineage/shared 0.0.0` (private), typescript `^5`, vitest `3.2.6`; created by PR #292 |
| Python API | `apps/api/pyproject.toml` | python `>=3.11`; fastapi `>=0.111.0`, uvicorn `>=0.27.0`, pydantic `>=2.0.0`, structlog `>=26.1.0,<27.0.0`, httpx `>=0.27.0`; dev: ruff `==0.16.9`, mypy `==2.3.1`, pytest `>=8.0.0`, numpy `>=1.26.0,<2.5.0`, scikit-learn `>=1.5.0,<2.0.0`; control extra: psycopg[binary] `>=3.2.0,<4.0.0` |
| Python ML | `ml-requirements.txt` | MiniLM/classifier toolchain (shadow-only artifact `models/classifiers/minilm-shadow-v1.json`) |
| Python MCP | `oracle-mcp-requirements.txt`, `integrations/siliconflow-mcp/requirements.txt` | Bridge services in §2 |
| Ruby RAG | `apps/rag-ruby/Gemfile` (+ lockfile) | sinatra `~> 4.1`, puma `~> 6.5`, sequel `~> 5.95`, pg `~> 1.5`, sqlite3 `~> 2.0` |
| Ruby worker | `apps/ruby_worker/Gemfile` (+ lockfile) | pg `~> 1.5`, rack `~> 3.0`, minitest `~> 5.0` |
| Ruby control | `apps/control-ruby/Gemfile` (+ lockfile) | sinatra `~> 4.1`, puma `~> 6.6`, rack `~> 3.2`, pg `~> 1.5` |
| Containers | `Dockerfile` (repo root, API), `.devcontainer/` | API image from repo root context — a known extraction edge for `ayahos-core` (see runbook Phase 3) |
| Dependency automation | `renovate.json` | Renovate dashboard is issue #259; pending majors are approval-gated there, not applied by this phase |

Extracted-repo dependency notes: `ayahos-site` and `ayahos-admin` carry their own root
`package.json`/`pnpm-lock.yaml`/`pnpm-workspace.yaml` (verified present in §1 tree reads).
`packages/shared` is currently a monorepo workspace member; any Phase 2/4 extraction must
decide how the extracted site/admin repos consume it (vendored copy vs published package)
— **not decided in this phase**.

---

## 4. Security / secrets inventory — NAMES AND LOCATIONS ONLY

No secret values are recorded here, and none move in this phase. Sources:
`.env.example` (190 keys — the local/runtime contract), `render.yaml` (105 `sync: false`
entries across services), `deploy/service-inventory.json` (per-service environment
contracts), `apps/site/wrangler.jsonc`, and the bridge README.

### Where secrets live today

| Location | What it holds | Notes |
| --- | --- | --- |
| Render service env (per service) | All `sync: false` values in `render.yaml` (provider keys, DB URLs, runtime/site keys) | Values set in Render dashboard only; blueprint carries names + non-secret defaults |
| Cloudflare Pages project `ayahos` (encrypted secrets) | Public site key used by Pages Functions | Preview deployments must never receive the production value (wrangler.jsonc comment) |
| Cloudflare Worker `octopus-github-bridge` (Worker secrets) | `GITHUB_STATUS_TOKEN` — **still missing**; also Octopus-side webhook config | Missing token is the standing blocker for enforceable `octopus/verify` (see §5) |
| Local/dev | `.env` files from `.env.example` | Never committed; repo secret rules in `AGENTS.md` |

### Secret-name families an extraction must re-issue (never copy) per repo

- **Site (`ayahos-site`):** the Pages site credential (`GOBLIN_SITE_API_KEY` /
  `DUAL_LINEAGE_SITE_API_KEY` family), `DUAL_LINEAGE_PUBLIC_RATE_LIMIT_URL` (non-secret
  var, in wrangler.jsonc), `TAVILY_API_KEY` (public-chat grounding, server-side only).
- **Core (`ayahos-core`):** `DATABASE_URL`, `DUAL_LINEAGE_RUNTIME_API_KEY`,
  `DUAL_LINEAGE_SITE_API_KEY`, `DUAL_LINEAGE_RAG_SERVICE_TOKEN`,
  `DUAL_LINEAGE_OPERATIONAL_REVIEW_SECRET`, `DUAL_LINEAGE_TELEMETRY_HASH_KEY`,
  `DUAL_LINEAGE_SANDBOX_WORKER_SECRET`, `DUAL_LINEAGE_SHADOW_REMOTE_SECRET`,
  provider keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DASHSCOPE_API_KEY`,
  `COHERE_API_KEY`, `DEEPSEEK_API_KEY`, `GROQ_API_KEY`, `GOOGLE_AI_API_KEY`,
  `AZURE_API_KEY`, `AWS_BEDROCK_API_KEY`/`AWS_BEARER_TOKEN_BEDROCK`,
  `HUGGINGFACE_API_KEY`, `SILICONFLOW_API_KEY`, `TOGETHER_API_KEY`,
  `ALPHA_VANTAGE_API_KEY`).
- **Admin (`ayahos-admin`):** `GOBLIN_API_KEY`, `GOBLIN_REVIEW_ACCESS_TOKEN`,
  `GOBLIN_OPERATOR_SECRET`, `GOBLIN_DEPLOYMENT_ROLE` /
  `NEXT_PUBLIC_GOBLIN_DEPLOYMENT_ROLE` (role flags, not secrets, but access-relevant).
- **Platform (`ayahos-platform`):** Octopus API credentials (held in Octopus, not in
  this repo), the bridge's `GITHUB_STATUS_TOKEN`, webhook secrets
  (`GITHUB_WEBHOOK_SECRET`, `GOBLIN_DEPLOYMENT_WEBHOOK_SECRET`,
  `GOBLIN_PROVIDER_WEBHOOK_SECRET`, `GOBLIN_PAYMENT_WEBHOOK_SECRET`,
  `GOBLIN_MONITORING_WEBHOOK_SECRET`, `GOBLIN_INGESTION_WEBHOOK_SECRET`).
- **Workloads (`ayahos-workloads`):** `DUAL_LINEAGE_RAG_DATABASE_URL` /
  `DUAL_LINEAGE_RAG_EMBEDDING_API_KEY`, `DUAL_LINEAGE_UNDERMIND_RAG_EMBEDDING_API_KEY`,
  `DUAL_LINEAGE_SPINE_DATABASE_URL`, `DUAL_LINEAGE_INCIDENT_DATABASE_URL`,
  `DUAL_LINEAGE_SANDBOX_WORKER_URL` + secret, node/compute credentials under
  `deploy/oracle/` examples.

Full key list: the 190 names in `.env.example` at the inventory SHA are the contract of
record; this section names only the security-relevant subset. A comprehensive
committed-history secret audit is still **pending** (runbook checkpoint, 2026-10-21) and
remains required before any extracted repo's history is treated as clean.

---

## 5. Database inventory

| Fact | Value at inventory SHA |
| --- | --- |
| Migration set | `apps/api/src/dual_lineage/db/migrations/` — 22 SQL migrations, `001_initial.sql` → `022_route_health_outcomes.sql` (latest: `022_route_health_outcomes`) |
| Migration runner / tests | `apps/api/src/dual_lineage/db/migrations.py`, `apps/api/tests/test_database_migrations.py` |
| Engine | PostgreSQL (psycopg 3) with pgvector (`017_enable_rag_pgvector.sql`); SQLite used for local/import paths (`import_sqlite.py`) and Ruby-side tests |
| Consumers | API (Spine `005_shared_spine.sql`, incidents `007`, provider metrics `008`/`009`, release evidence `018`), Ruby workflow queue (`002`, `011`–`013`, `015`), Ruby RAG (`014`, `017`, `021` — `rag_chunks` + `undermind_rag_*` tables) |
| RLS | Private storage/runtime/rag tables hardened by `003`, `004`, `016` |
| Rollback posture | Expand/contract discipline per runbook Phase 3; no destructive down-migration is part of any migration phase in this program |

DB connection strings are secrets (§4) and do not move in this phase. Which extracted
repo owns migrations is a Phase 3 decision (core is the natural owner); **undecided**
here.

---

## 6. CI / release inventory

| Lane | Owner | State at inventory SHA |
| --- | --- | --- |
| Octopus Deploy (primary) | `.octopus/deployment_process.ocl` — 7 gates: API/PostgreSQL, web/site, ML, RAG/pgvector, Ruby worker, Ruby control, release-hardening | Configured. A committed process is not proof of execution; no Octopus task was inspected in this run, so the latest full-release result is **unverified** here. RAG worker exit 137 remains an open investigation (issue #243; runbook Phase 0/5). |
| `octopus/verify` GitHub status | `deploy/octopus-github-bridge` (Cloudflare Worker) | Advisory only: rulesets return 403 on this private free-plan repo, and the Worker's `GITHUB_STATUS_TOKEN` (fine-grained, this repo only, Commit statuses read+write) is still pending on the owner — first setup attempt did not land on the Worker. Merges currently ride on local gates. |
| Canary | `scripts/ci/canary.sh` (public, secrets-free subset) + daily timer (~08:11 local) | Configured; last recorded run green end-to-end on 2026-10-21 (PR #266 contract fix). |
| Post-deploy checks | `scripts/ci/post-deploy.sh` → `scripts/live_e2e.sh`, `scripts/ci/live-release.sh` | Configured as the Octopus `live` lane; evidence about the live stack, not a merge gate. |
| Local gate | `make check` + focused lanes (`make api-test`, `make web-test`, `make type-check`, `make ruby-client-check`, `make consistency-check`, …) | Per `AGENTS.md` verification contract. |
| Drone | `.drone.yml` | On-demand standby only; not acceptance evidence. |
| GitHub Actions | — | None in the monorepo (retired; new workflows need an architecture decision). Extracted repos run their own bounded Actions verification per the runbook checkpoints — that allowance does not extend to this repo. |
| Renovate | `renovate.json`, dashboard issue #259 | Configured; majors approval-gated. |

---

## 7. Rollback baseline

- **Baseline SHA:** `923f6bc51233a82732dab81e4b0a70eed62d9171` on `main`. Every future
  phase records its own pre-phase SHA the same way before changing anything.
- **Canonical source rule:** the monorepo stays canonical and production-bound until a
  phase's acceptance evidence exists (destination repo + exact commit + hosted
  deployment SHA + accepted test run + rollback evidence, per issue #243 tracking).
  No phase in this program deletes, renames, or transfers the monorepo.
- **Per-surface rollback:**
  - *Cloudflare Pages (site):* redeploy the previous Pages deployment / re-point the
    Pages Git integration to the monorepo; production currently builds from the
    monorepo, so Phase 2 rollback = revert the integration change only.
  - *Vercel fallback (site):* pinned build `4999457` stays as the frozen fallback;
    validate `/backup` before and after any site cutover (runbook Phase 2).
  - *Render (API + web):* Render keeps prior deploys; rollback = redeploy the last
    verified SHA (`EXPECTED_SHA` convention in `scripts/ci/post-deploy.sh`). Blueprint
    changes roll back by reverting `render.yaml` on `main`.
  - *Database:* no schema change is bundled with any GitHub-path change (standing
    constraint); DB rollback is therefore decoupled and follows expand/contract.
  - *Octopus:* process changes are configuration-as-code in `.octopus/`; rollback =
    revert the OCL change and re-publish the prior process version.
- **$0 guardrail:** every surface above runs on free tiers (Render free, Pages free,
  GitHub Free org). No phase may introduce a paid service, and quota/billing state is
  part of each phase's evidence.

---

## 8. What this phase changed in the manifest

`migration/repositories.json` was updated only where this run's API verification
supports it: org ID and Phase 0 verification facts were added, per-repo
`phase0_verification` records (repo ID, default branch, tree entry count,
permissions) were added, and the `ayahos-platform` / `ayahos-workloads`
`extraction_status` lines now reflect the verified tree presence above. Deployment
statuses were **not** changed — nothing was deployed from a new repo in this phase,
and no status was inflated from documentation alone.

## 9. Next step — Phase 2 (site extraction verification)

Phase 2 is **not started** by this PR. Its concrete next action, per the runbook:

1. In `ayahos-hq/ayahos-site`, bring the extracted snapshot current with monorepo
   `main` (it predates PRs #284–#292, including the new `packages/shared` dependency —
   resolve the shared-package question in §3 first), then run its standalone gates
   (frozen install, lint, type-check, unit + Playwright) at an exact SHA.
2. Only after standalone green: a secret-free preview deployment, with production
   Cloudflare still bound to the monorepo and the Vercel pinned fallback validated.

**Blockers for Phase 2:** (a) the `packages/shared` consumption decision for extracted
repos; (b) the owner's org-settings hardening in §1 if "minimal permissions" is treated
as a Phase 2 entry condition; (c) `GITHUB_STATUS_TOKEN` still missing on the bridge
Worker, so no merge in any repo is yet gated by `octopus/verify`.
