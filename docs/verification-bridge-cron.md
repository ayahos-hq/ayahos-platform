# HQ verification bridge: production cron and the KV list cap

Status: live change applied 2026-11-21. This note is the durable record; it
deliberately lives outside the attested extraction tree (deploy/, scripts/,
.octopus/, docs/infrastructure/), whose files are pinned byte-for-byte to the
monorepo snapshot in SOURCE-PROVENANCE.json and must not be edited.

## What is live

- Worker: `ayahos-hq-verification-bridge` (Cloudflare account `AyahOS_HQ`,
  265071fc5a2ac8bbe85e2bd724361080).
- Cron trigger: `*/2 * * * *` (every 2 minutes), set through the Cloudflare
  API on 2026-11-21 and verified by read-back. Health endpoint returns 200.
- The cron exists only on the deployed Worker. The committed HQ config
  (deploy/hq-verification-bridge/wrangler.jsonc) intentionally has no cron:
  it is a Workers Builds preview contract, and the CI gate
  (scripts/ci/check_hq_worker_build.py) rejects a cron there.

## Why it changed

- The previous cron was `* * * * *` (every minute). Each reconcile tick calls
  `env.TASKS.list()` once, so the bridge burned 1,440 KV list operations per
  day against the free plan cap of 1,000/day.
- On 2026-11-21 the account hit 90% of the cap at 15:07 UTC and exceeded it
  at 16:47 UTC. While capped, list() throws outside the per-task error
  handling, the tick aborts, and `octopus/hq-operator-verified` outcome
  statuses stall until the 00:00 UTC reset. No task records are lost (KV
  entries persist, 7-day TTL); pending-status webhooks are unaffected.
- At every 2 minutes the bridge uses 720 lists/day, under the cap with
  headroom. Outcome statuses now post within ~2 minutes instead of ~1.

## Trap for future deploys

- deploy/octopus-github-bridge/wrangler.jsonc is the legacy monorepo bridge
  config, pinned in SOURCE-PROVENANCE.json. It still contains
  `"crons": ["* * * * *"]` and a placeholder KV id. Do not deploy the HQ
  Worker from it: it would restore the per-minute cron and re-break the cap
  (and the placeholder KV id would break the bridge outright).
- The legacy Worker `ayahos-octopus-github-bridge` is not deployed in either
  Cloudflare account (verified 2026-11-21, schedules endpoint 404 in both);
  it is retired with the archived monorepo and burns no quota.
- If the reconcile cadence ever needs to change again, change the deployed
  Worker's schedule (dashboard or API), keep the daily list budget under
  1,000, and update this note in the same change.
