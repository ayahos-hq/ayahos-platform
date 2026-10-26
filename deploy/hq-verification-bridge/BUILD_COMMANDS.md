# HQ verification Worker: Cloudflare Builds source/preview contract

This directory is **only** for the HQ verification Worker, not the deployed
`ayahos-octopus-github-bridge` (monorepo release gate). Its Worker source is
shared read-only from `../octopus-github-bridge/src/worker.js`, whose bundle
was confirmed byte-for-byte identical to the live HQ Worker on 2026-10-26.
The two Workers have **different bindings**, deployment identities and
GitHub/Octopus authority. Keep both configurations separate.

## Approved Cloudflare Workers Builds settings (apply to existing HQ Worker)

- Git repository: `ayahos-hq/ayahos-platform`; production branch: `main`.
- Root directory: `/` (repository root), **not** the bridge subdirectory.
- Build command:
  `python3 scripts/ci/check_hq_worker_build.py --preview-only && python3 scripts/verify-platform.py && python3 scripts/verify-release-manifest.py && node --test deploy/octopus-github-bridge/test/worker.test.js`
- Preview command:
  `npx wrangler@4.152.0 preview --config deploy/hq-verification-bridge/wrangler.jsonc --worker-name ayahos-hq-verification-bridge`
- Production deploy command: `npx wrangler@4.152.0 deploy --dry-run --config deploy/hq-verification-bridge/wrangler.jsonc`.
  **This intentionally DOES NOT deploy**: the hosted check validates the code
  but existing Octopus/HQ governance retains release authority. It must not be
  changed to a live production upload without a separate independent review.

The environment variables `WORKERS_CI`, `WORKERS_CI_COMMIT_SHA`, and
`WORKERS_CI_BRANCH` are injected by Cloudflare Builds. The Python gate
fails if the working tree HEAD differs from `WORKERS_CI_COMMIT_SHA` or when
the explicit preview-only guard is absent, preventing branch-switching
or PR misattribution. Never overwrite `WORKERS_CI_COMMIT_SHA` in custom
build variables.

## Safety

- The Wrangler 4.152 Worker Previews configuration explicitly declares preview
  variables and KV; omitting `previews` causes Wrangler to reject preview builds.
- The committed KV ID belongs to **preview only** and is physically separate
  from production TASKS. The preview config contains no Octopus/GitHub
  secrets; a preview cannot submit authenticated verification jobs.
- There is deliberately no cron trigger in this preview config. The deployed
  production HQ Worker retains its existing `* * * * *` cron and secrets.
- The committed config is **not** a production deployment manifest.
  Do not use it to deploy or mutate the production HQ Worker.
- Preserve the existing Worker build token and its GitHub connection.
  Do not create a new competing CI status or bridge.
- The old Builds root pointed at the monorepo bridge config, with a different
  Worker name and the placeholder `REPLACE_WITH_KV_NAMESPACE_ID`.
  This was not production safe. If a Cloudflare build still uses those values,
  it is not a valid verification for this repository.
- Verify an exact-commit preview and a passing GitHub check before merging.
  Preview compilation alone is not end-to-end release acceptance.
- Source of truth for Cloudflare CLI settings: https://developers.cloudflare.com/workers/ci-cd/builds/configuration/
- The default CI commit variable is documented at
  https://developers.cloudflare.com/changelog/post/2025-06-10-default-env-vars/
