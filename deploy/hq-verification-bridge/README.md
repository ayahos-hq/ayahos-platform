# AyahOS HQ verification bridge

HQ-only Cloudflare Worker directory for the `ayahos-hq-verification-bridge`
Worker in the **AyahOS_HQ** Cloudflare account. It is the Octopus/GitHub
verification bridge for the five `ayahos-hq` repositories, posting the
`octopus/hq-operator-verified` commit status. The canonical status context,
Octopus project, and repository values are in `wrangler.jsonc` and are
guarded by `scripts/ci/check_hq_worker_build.py`.

This directory exists because the Workers Builds trigger for this Worker
(build + deploy dry-run on every push to `main` of `ayahos-hq/ayahos-platform`)
references this manifest. The trigger was configured on 2026-10-25 but the
referenced files were never committed, so every triggered build failed at
the first command (`scripts/ci/check_hq_worker_build.py` missing). See
ayahos-hq/ayahos-platform issue #47.

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
