# Three-way repository divergence audit and staged authority transfer

**Observed 2026-10-23 UTC; read-only GitHub tree inspection.** This report is a comparison of Git *blob identities*, not a live deploy, test pass, dependency compatibility certification or proof of runtime state.

## Immutable evidence

- Canonical production source repository: `fuaadabdullah/AyahOS_Dual_Lineage`.
- Last shared extraction base: `a7ef41fe1ec6a680bc734a5d54890fb13972d3a3`.
- Current source `main`: `dbf9fbde52a11bbc069e19bdeca2658d8dcc1147`, 50 commits past extraction base, 86 changed files in GitHub's compare API.
- Current destination heads (all `main`):
  - site: `539c3bc609cfd8eaad34f7c97046fcbc6cb798bb`
  - core: `0be54c8c36836a310c9781413daa0f4cb63f7801`
  - admin: `b6180662d0dabfead1021f8477ff67bf08087e89`
  - platform: `e2d69fd7a8fe20a59f6cdb7a1bdd541a9ea65588`
  - workloads: `60f76203de45a1c340eb7bfea89a29b2abcfcbca`

All seven queried recursive GitHub trees returned `truncated=false`. Counts compare all paths within the documented service-prefix scopes, including paths absent on one side. The platform extraction is curated: monorepo-only platform paths outside the destination provenance can include work **intentionally not yet extracted**, not necessarily an inadvertent regression. This is a triage inventory, not a safe auto-merge list.

| Target | Monorepo-only | HQ-only | Both changed incompatibly | Total distinct paths |
| --- | ---: | ---: | ---: | ---: |
| site | 4 | 3 | 0 | 7 |
| core | 16 | 24 | 3 | 43 |
| admin | 4 | 3 | 2 | 9 |
| platform | 31 | 2 | 4 | 37 |
| workloads | 5 | 0 | 0 | 5 |
| **Total** | **60** | **32** | **9** | **101** |

**Manual reconciliation first:** these paths changed independently from the extraction baseline.

- `apps/api/src/dual_lineage/db/migrations.py`
- `apps/api/src/dual_lineage/providers/factory.py`
- `apps/api/src/dual_lineage/runtime.py`
- `apps/web/app/control/page.tsx`
- `apps/web/lib/contracts.ts`
- `scripts/ci/verify.sh`
- `scripts/db/postgres_env.py`
- `scripts/db/rehearse_recovery.py`
- `scripts/db/restore_verify.py`

Do **not** cherry-pick or deploy the HQ strict-free quota/route work straight to production. Its safety model spans `ayahos-core`, `ayahos-site` and `ayahos-admin`; reconcile schema migrations, free-route admission, API compatibility, SSE and fallback before promoting. Likewise preserve changes to backups, recovery and Octopus in the source monorepo until the integrated replacement passes.

## Reproduce on an authorized worker

Install no third-party Python dependencies. Supply a least-privilege token **only through the runtime secret store**, with read access to the six repositories:

```sh
python3 -m unittest discover -s scripts -p 'test_audit_repo_drift.py' -v
python3 scripts/audit-repo-drift.py --manifest release-manifest.json --output drift-report.json
python3 scripts/audit-repo-drift.py --manifest release-manifest.json --enforce
```

The last command deliberately exits 2 while drift remains. A 0 means Git source alignment at the exact scanned SHAs, **not cutover authorization**. Missing credentials, insufficient access, network failure or truncated trees fail closed. Record the generated report as an Octopus non-secret artifact, not in public telemetry. The script reads blobs (hashes) and does not download or diff secret contents. Report output includes repository paths and Git SHA metadata.

## Single-authority rules

1. **Before each service cutover**, the monorepo owns production changes; a destination is a provisional copy with explicitly reviewed independent additions. No dual-writers for deployed service configuration.
2. **After that service's verified cutover**, its HQ repository becomes canonical for its owned paths. Put an automated change-denial rule over the corresponding monorepo paths and redirect fixes to the HQ repo. Do not archive the monorepo before every service is stabilized.
3. The `ayahos-platform` repository coordinates immutable releases; the independent HQ Octopus project must fetch exact component SHAs and verify content digests plus the cross-service acceptance suites. **GitHub Actions' source-isolation tests are not the authoritative production release check.**
4. `ayahos-core` keeps the single deterministic Undermind/Action Gateway/Shared Spine authority. Ruby workers, Node 001 and the public site do not become alternative authorization authorities.
5. Cloudflare Pages is the site primary. Keep the original deployment and frozen Vercel fallback for reversible site migration; never cut DNS, database, secrets and service source in one step. Preserve the $0 infrastructure budget and do not place heavy ML/pgvector on undersized free web runtimes.

## Required transitions (none attested complete here)

- **P0 drift reconciliation:** resolve the nine overlapping files first, classify the 92 one-sided files, synchronize intentionally chosen changes into isolated HQ branches, run full relevant tests and record branch SHAs.
- **P1 release authority:** create a separate HQ Octopus project and bridge, keep the original monorepo bridge unchanged, replace all monorepo-relative script references with immutable fetched component artifacts, establish pgvector/Ruby/Policy/SSE integration gates and an explicit artifact-digest bill of materials. Diagnose the observed exit 137 rather than skipping RAG.
- **P2 service-by-service cutover:** staged site preview with no production credential, identity/SSE/auth/regression checks and tested rollback; then separately assess admin, core and workers. Move each only with operator-approved deploy settings and live evidence.
- **P3 enforce single writers:** after each verified cutover, gate edits and deployments from its old monorepo paths, amend the owner manifest, watch errors and rollback signals, and retain the old source until the stabilization window completes.

The current `release-manifest.json` is only `candidate`, with null artifact digests and pending Octopus, database recovery, authenticated smoke and rollback attestations. **No production cutover is authorized by this audit.** See original migration issue #243.
