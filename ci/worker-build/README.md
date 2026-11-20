# HQ verification Worker: non-deploying CI overlay

This directory is a **new, reviewable operational overlay**, separate from the
immutable imported files listed in `SOURCE-PROVENANCE.json`. It corrects a
contradiction in the archived
`scripts/ci/check_hq_worker_build.py`: that script rejects the committed
production `TASKS` KV ID and demands identical preview and production IDs.
The reviewed Wrangler config rightly uses **separate** namespaces.

## Intended Cloudflare Workers Builds settings (not applied by this PR)

Use only after examining the actual failing Cloudflare build logs, confirming
the Worker belongs to `AyahOS_HQ`, and validating the exact PR SHA:

- Repository: `ayahos-hq/ayahos-platform`
- Root directory: `/`
- Production branch: `main`
- Build command:

  ```sh
  python3 ci/worker-build/check.py --preview-only &&
  python3 -m unittest discover -s ci/worker-build -p 'test_*.py' -v &&
  python3 scripts/verify-release-manifest.py &&
  node --test deploy/octopus-github-bridge/test/worker.test.js
  ```

  The overlay itself invokes `python3 scripts/verify-platform.py` (pinned
  provenance and Octopus topology checks) on every real build.

- Preview command (same reviewed previous contract):

  ```sh
  npx wrangler@4.152.0 preview --config deploy/hq-verification-bridge/wrangler.jsonc --worker-name ayahos-hq-verification-bridge
  ```

- Production deploy command (must remain **dry run only**):

  ```sh
  npx wrangler@4.152.0 deploy --dry-run --config deploy/hq-verification-bridge/wrangler.jsonc
  ```

- Never override `WORKERS_CI_COMMIT_SHA`, `WORKERS_CI`, or
  `WORKERS_CI_BRANCH`; the guard requires an exact Git HEAD match.
- Do not copy production TASKS KV into the preview binding. The overlay pins
  each namespace ID separately and rejects additions to approved
  non-secret authority bindings.
- Do not change or deploy the original monorepo Worker, existing Cron trigger,
  GitHub status writer, or Octopus secret/authorization paths.

## Offline test and acceptance

```sh
python3 -m unittest discover -s ci/worker-build -p 'test_*.py' -v
python3 scripts/verify-platform.py
python3 scripts/verify-release-manifest.py
node --test deploy/octopus-github-bridge/test/worker.test.js
```

These local tests are **not** proof of a passing Cloudflare hosted build.
Before merging or changing Cloudflare Builds settings, review the hosted error
log, confirm the exact SHA and account, rerun a hosted **preview-only** build
with all checks passing, and preserve `octopus/hq-operator-verified` plus
all other required release checks.

No Cloudflare setting is modified by this PR. Do not replace a failed
Cloudflare check with a synthetic successful GitHub status.
