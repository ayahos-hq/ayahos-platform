# Linux-first release gates and non-regression contract

**Status:** proposed P0 acceptance contract, 2026-10-24 UTC. This is not a passed release certification. See [the observed source and runtime baseline](./linux-release-baseline.md) before changing Linux toolchains, Octopus projects, production routing, or repository ownership.

## Architecture invariants: must remain unchanged

1. **Deterministic Undermind authority:** Overmind proposes and reasons but cannot directly execute write, network or shell actions. Shadow classifiers and critics cannot override deterministic policy.
2. **Shared Spine integrity:** request identity, control outcome, terminal SSE, usage, trace and interruptions remain correlated. Preserve budget, cancellation, timeout and cost limits.
3. **Action Gateway:** every effectful action stays behind policy, authorization and confirmation; unexpected failure is deny-by-default.
4. **Customer chat:** existing authentication, encrypted site-key boundaries, rate limits, SSE terminal events, provider ordering/fallback and production failure behavior are preserved.
5. **Data safety:** migrations are compatible with current deployed readers/writers; no production backup deletion, restore to live DB or accidental schema promotion. Ruby RAG requires real PostgreSQL 16 plus pgvector in its certification lane, never a skipped or SQLite substitute.
6. **Operational separation:** Cloudflare/Vercel customer edge, managed runtime, Octopus acceptance and Node 001 inference remain separately permissioned. Developer WSL must never be the only always-on release or serving host.
7. **Cost/secret ceilings:** no credentials in Git or logs, no persistent tokens transferred into untrusted preview environments, no added paid cloud workers or commercial hosting assumptions without account-level evidence.

The source-of-truth architectural invariants live in [AGENTS.md](../../AGENTS.md). A change to any of them needs an explicit architecture decision, focused negative tests and authorized deployment review. The Linux program is **not** permission to alter control semantics.

## Evidence and exact-SHA gates

| Gate | Concrete pass evidence | Current P0 status |
| --- | --- | --- |
| A. Source inventory | Monorepo and all five HQ branch SHAs, manifest ownership, source differences and current deployment IDs recorded | **Partial:** GitHub SHAs verified; production API SHA and release ownership still need authenticated review |
| B. Baseline regression | `make check` on canonical current source, focused chat/auth/SSE/policy and Ruby client tests; test names/counts and environment recorded | **Pending** for full baseline; no passing claim |
| C. Linux reproducibility | Native Ubuntu 24.04 filesystem/workspace, per-component Python/Node/Ruby versions, exact lockfiles and repeatable setup; avoid using `/mnt/c` for build work | **Pending**; local WSL Ubuntu exists but all component toolchains not yet installed |
| D. HQ build input | Five component commits exactly match an immutable release manifest, with ABI/schema checks and binary artifact SHA-256 digests | **Pending:** candidate manifest has unknown artifact digests |
| E. CI authority | Dedicated isolated HQ Octopus project, exact pushed SHA, required test tasks and logs, status linked to **same commit**; monorepo bridge untouched | **Pending** for HQ. Monorepo `octopus/verify` status alone is not HQ evidence |
| F. Heavy real contract | Disposable PostgreSQL 16/pgvector, Ruby RAG tests and SQL contract migration checks complete without skipped tests; worker memory and SIGKILL/exit 137 investigated | **Pending** |
| G. Staging behavior | Known deployment artifact digest, authenticated chat, complete SSE, cancellation, provider fallback, policy denial, telemetry, admin, RAG and gateway probes | **Pending** |
| H. Database recovery | Restorable backup to isolated instance, verified data integrity/schema, measured recovery and tested rollback to prior revision | **Pending** |
| I. Production canary | Approved individual service release, deployed exact SHA/digest, rate-limited smoke, unchanged critical metrics, rollback pointer and owner approval | **Pending** |
| J. Release authority cutover | Existing monorepo delivery retained until HQ verifier + service canary + rollback pass, no duplicate triggers or orphaned bridges | **Not authorized** |

A gate marked **pending** blocks only the dependent promotion, not independent documentation or isolated tests. The default is to **fail closed**, never to skip a failing test or infer green from missing statuses.

## Verification commands and scoping

Execute each command on a clean commit checkout; capture UTC timestamp, OS/runtime versions, source SHA, exit code, test count, and whether credentials/services were involved.

```sh
# Read-only working tree and source identity (before/after each change)
git rev-parse HEAD
git status --porcelain
git ls-files -s

# Platform candidate: cheap offline regression on Ubuntu 24.04
python3 scripts/verify-platform.py
python3 scripts/verify-release-manifest.py
python3 scripts/run-hq-offline-tests.py
node --test deploy/octopus-github-bridge/test/worker.test.js

# Original monorepo: full stack gate only after per-service dependencies are provisioned
make check

# Dedicated registry gateway source checkout
cd services/registry-gateway && npm test
```

The **platform candidate** commands above are run from `ayahos-hq/ayahos-platform`, not from the monorepo. The gateway command also belongs to that platform checkout, not the monorepo. Do not run scripts by guessing the wrong repository path. If a command is missing from a particular SHA or its runtime dependencies are absent, record that as **not run** and block the relevant gate.

The `make check` target uses the monorepo's defined Python and web test suite; Ruby RAG and PostgreSQL/pgvector require additional separate verified CI lanes. A passing `make check` is **not** a complete release attestation.

## Acceptance workflow (one verifiable slice per PR)

1. Inventory exact source and deployment revision; inspect overlapping PRs and existing behavior.
2. Write a failing regression test first for any new or changed logic. Pure documentation/read-only inventory requires evidence review instead.
3. Change only the owning component. Use a separate branch/worktree and Linux-native paths. Never mass-upgrade Node, Python and Ruby versions together.
4. Verify focused tests, all relevant mandatory component suites, whitespace, security boundaries and change diff against the same SHA. Record **what was not tested**.
5. Attach evidence to a draft PR. Promote from draft only after the actual authoritative Octopus run and required review pass for that scope.
6. Deploy to isolated staging, not to production, unless the release checklist identifies a safe canary and tested rollback.
7. Preserve the old component and trigger until the new one has passed the soak period and explicit cutover gate.

### Merge and rollback constraints

- **Documentation-only P0 PR:** may merge once reviewed for accuracy and without changing runtime paths, CI authority or deployment settings. No live smoke is claimed.
- **Behavior/CI/config PR:** must show exact-SHA Linux regression and all affected contract/Octopus checks before merge; cross-repo drift must be reconciled.
- **Production service promotion:** needs matching release SHA/artifact digest, passing staging proof, protected credentials, owner-approved traffic scope and version-pinned rollback.
- **Rollback:** restore the last known verified artifact/configuration, not a guessed branch head; prefer reversible traffic routing over reconstructing a prior binary. Never downgrade a schema without validated compatibility.
- **Registry gateway:** authenticated read-only `agents:search` via approved protected credentials, Vercel WIF, sanitized negative responses and linked Octopus verification are prerequisites for gateway PR merge or discovery activation. Publishing/routing/execution stay off.

## Evidence record for each future task

```text
UTC timestamp:
Repository / branch / full commit SHA:
Runtime OS + interpreter/container versions:
Environment: local | Octopus verification | isolated staging | production
Build artifact digest and deployed identifier (if applicable):
Exact commands / HTTP paths:
Observed exit codes, test counts, status and duration:
Auth used? (yes/no; NEVER record secret values):
Negative control / no-regression checks:
Remaining unknowns or skipped checks:
Rollback target and decision: GO | HOLD
```

**P0 decision:** HOLD on HQ cutover, production deployment, infrastructure re-pointing, wholesale toolchain upgrades and registry publishing/routing until missing evidence is independently obtained. No production state was modified when recording these gates.