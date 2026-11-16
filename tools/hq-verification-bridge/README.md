# AyahOS HQ verification bridge

HQ-only Cloudflare Worker directory for the `ayahos-hq-verification-bridge`
Worker in the **AyahOS_HQ** Cloudflare account. It is the Octopus/GitHub
verification bridge for the five `ayahos-hq` repositories, posting the
`octopus/hq-operator-verified` commit status. The canonical status context,
Octopus project, and repository values are in `wrangler.jsonc` and are
guarded by the `check_hq_worker_build.py` next to it.

The `tools/` directory holds the HQ-only build inputs. The extraction under
`deploy/` and `scripts/ci/` is tracked by `SOURCE-PROVENANCE.json` and checked
by `scripts/verify-platform.py`. Workers Builds expects these inputs under
`tools/hq-verification-bridge/` from the root of `ayahos-hq/ayahos-platform`.
See ayahos-hq/ayahos-platform issue #47.

Boundaries:

- `src/worker.js` starts from the same bridge implementation as
  `deploy/octopus-github-bridge/src/worker.js` (the monorepo bridge). The
  two Workers are separate deployments in separate Cloudflare accounts
  with different repositories, Octopus projects, status contexts, and KV
  namespaces. Never deploy one directory's config over the other Worker.
- Nothing here deploys for real: the build trigger's deploy step is a
  `wrangler deploy --dry-run`. The live Worker (version 7, deployed
  2026-10-25) is changed only through its own reviewed release process.
- Secrets (`GITHUB_WEBHOOK_SECRET`, `GITHUB_STATUS_TOKEN`,
  `OCTOPUS_API_KEY`) exist only in the deployed Worker's settings. They
  are never committed; `check_hq_worker_build.py` fails the build if a
  secret-shaped variable appears in the manifest's `vars`.

## Selecting and checking Octopus revisions

The HQ bridge uses the database-backed `AyahOS HQ Verification` project in
`Development`. It discovers the project's Git-backed actions from the
Octopus release template. Platform actions use the signed push SHA. Each
sibling action uses the pin from `release-manifest.json` at that exact
Platform commit.

Before it queues Development, the bridge reads back the release and its
process snapshot and checks the repository and commit for every selected
Git resource. A missing or different selection produces an error status.
Tasks queued by an older bridge need a fresh run to earn a success status.
The status covers the gates actually configured in the HQ Development
project. Complete release acceptance needs the separate cross-repository,
artifact, and live gates described in [the candidate verification guide](../../docs/infrastructure/octopus-ci-verification.md).
