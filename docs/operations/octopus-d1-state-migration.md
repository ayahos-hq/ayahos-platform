# Octopus bridge CI metadata storage: KV -> D1 (2026-10-23)

## Proven failure and root cause

Cloudflare Workers observability recorded **`KV put() limit exceeded for the day`** on the signed push webhook for commit `75ad3cd9427e3062d3866fbcf94f084574aebe7e`. The Worker attempted to write both `result:<sha>` and `task:<OctopusTask>`, and KV rejected the operations. This was *not* a missing GitHub/Octopus credential. Octopus tasks also independently reported failures on P1/P2; those failures require task log analysis and are not magically fixed by storage migration.

On the Workers Free plan KV permits **1,000 written keys per UTC day**. The bridge already polls every 6 minutes, and repeated branch updates, task status changes and pagination cursor updates exhausted the write allowance. Cloudflare D1 Free provides **100,000 rows written/day**, 5 million rows read/day and 5 GB storage across D1. D1 is a dedicated Octopus CI **transient status ledger only**. It is NOT a second application database, model-token quota ledger, or a mirror of production Supabase.

Official: https://developers.cloudflare.com/workers/platform/pricing/

## Verified Cloudflare metadata

- Worker: `ayahos-octopus-github-bridge`; exact main repository `fuaadabdullah/AyahOS_Dual_Lineage`.
- Existing KV `TASKS`: `4883e599d9f3439eb82d2e81a23f2557`.
- Dedicated D1 (US jurisdiction): `ayahos-octopus-bridge-state`, `208f81a8-81b8-47d4-aa69-e150af060798`.
- Created isolated D1 schema `bridge_state(name TEXT PRIMARY KEY, value TEXT, expires_at INTEGER)` plus TTL index on 2026-10-23. Database contains **no inference prompts, API keys, secrets or user chat content**.
- Current production Worker binding names `GITHUB_STATUS_TOKEN`, `GITHUB_WEBHOOK_SECRET`, `OCTOPUS_API_KEY` are already present as managed `secret_text`, not source values. Never replace or read their values.
- **Live read-only audit on 2026-10-23:** the deployed Worker setting is `STATE_BACKEND=d1`, with `STATE_DB` bound as D1, `TASKS` KV retained and `BRANCH_QUEUE_ENABLED=false`. Cron remains `*/6 * * * *`; the three original secret binding *names and types* were present. The committed `wrangler.jsonc` default was aligned to `d1` to prevent a future source deployment from silently reverting production to KV.
- D1 binding alone does not cut over; only `STATE_BACKEND=d1` selects D1. `STATE_BACKEND=kv` remains an explicit rollback switch, subject to KV quota availability.
- Read-only D1 query observed 241 result keys, 12 desired keys, 4 attempted keys and 0 active tasks; no values, secrets or user content were read. Later a new Octopus task was observed, so these counts are a point-in-time observation, not a fixed baseline.

## Source changes and security boundaries

- One DB-backed state facade in `src/d1_state.js` implements `get`, `put`, `delete`, `list` with the existing KV semantics, bounded keyset pagination, TTL validation, and explicit expiration-prune helper.
- **Free tier guard:** Cloudflare D1 Free permits 50 queries per Worker invocation. D1 reconciliation handles at most 10 tasks per tick (4 when branch-queue mode is enabled), and limits branch-queue scans to 4 entries per prefix in that mode. This leaves query headroom for metadata and bounded cleanup; higher volumes drain over later scheduled ticks, rather than claim immediate verification. See https://developers.cloudflare.com/d1/platform/limits/.
- **TTL guard:** each D1 scheduled tick calls `pruneExpired(100)` before reconciling; expired keys are otherwise invisible but physically retained. The finite prune batch prevents growth without unbounded queries.
- **Status duplication guard:** terminal tasks persist their last reported state before delete so a transient D1 delete error does not blindly repeat the GitHub status POST on the next tick. GitHub itself still needs idempotent/outage-safe reconciliation; this is not a distributed exactly-once guarantee.
- The deployed HMAC webhook, GitHub status writer, original Octopus release process, task mapping, branch queue, bounded polling cadence and /status response format are **unchanged**.
- The guarded `stateStoreEnv` maps the existing `env.TASKS` interface to D1 only under the explicit switch, so the rest of the bridge code is unchanged.
- Store names/values are private CI metadata; /status returns only an allowlisted state for an exact commit, no task URL or logs.
- D1 is not billed on Workers Free beyond free allowance: over-limit operations **fail** rather than incur pay-as-you-go charges. Monitor request/row counts and set a hard usage alert.
- There is no additional Worker Cron, no paid dependency, no extra task launches or new credentials.

## Live state versus historical migration steps

The numbered sequence below documents the original **pre-cutover procedure** and the rollback checks needed for a future redeploy. It must **not** be replayed unconditionally: read-only Cloudflare API checks on 2026-10-23 already showed `STATE_BACKEND=d1` in production, and a new exact-SHA PR verification was executing. Do not overwrite D1 with an older KV snapshot, change protected secrets, disable the six-minute schedule, or trigger an extra live Octopus task just to reconstruct this procedure.

For every future Worker deployment: first snapshot current version/settings (secret *names* only), verify script modules and six-minute cron, run offline `node --test deploy/octopus-github-bridge/test/*.test.js`, and require the existing exact-SHA Octopus verdict. Use strict binding inheritance and verify `STATE_BACKEND=d1` persists. No merge or live deploy on an unconfirmed or failed gate.

## Strict migration and rollback sequence (historical from KV baseline)

1. Keep `STATE_BACKEND=kv` live while testing source. Snapshot the deployed Worker version, all existing binding names/types, schedule, `/healthz` and two known `/status/<sha>` responses.
2. Create D1, apply `d1-schema.sql`, verify single bridge_state table and correct indexes; this was done. Do not apply schema to production Supabase.
3. Snapshot all *allowed* KV key prefixes (`task:`, `result:`, `desired:`, `attempted:`, `meta:`), preserving original JSON bytes and expiry. Backfill via idempotent D1 insert/upsert; verify total and individual known SHA states. **No secret values are ever fetched**.
4. Re-copy all still-live KV keys immediately before cutover. Do not delete KV. A conservative final sync should prefer latest old-KV state only during legacy operation and never overwrite a newer post-cutover D1 state.
5. Deploy the tested module bundle with strict binding inheritance (`bindings_inherit=strict`) retaining all existing secrets, KV, nonsecret vars and original 6-minute cron. First deploy with `STATE_BACKEND=kv`; check /healthz, HMAC 401, known /status states, schedule and no unexpected Octopus release. Roll back if mismatched.
6. Switch `STATE_BACKEND=d1` as a nonsecret setting, leaving the legacy KV binding intact. Probe the same status SHAs, then run a signed benign push through the existing GitHub webhook and verify exactly one Octopus task/status and eventual terminal status. Do not assert Octopus PASS unless the actual 8-step deployment passed.
7. Check new write/read counters stay below D1 Free daily caps, KV writes fall to zero, events remain redacted, and /status errors remain unknown on data loss. Run an exact-SHA end-to-end canary before approving PR merges.
8. For rollback, switch `STATE_BACKEND=kv` (after UTC allowance reset) or restore the previous Worker script **with its exact secret bindings**. During rollback, copy newer D1 task/status records back to KV if KV quota has sufficient room. Never erase the new D1 or old KV state until every prior task is terminal and the seven-day TTL has expired.

## P0 exact-SHA evidence and blockers

- Candidate PR #394 head `94f73285f4b3f8a53dcec9d5cf2cc2c4ab1c5d13` introduces bound D1 queries, cron expiration pruning, terminal acknowledgement, regression tests, and config alignment. The first observed Octopus task was `ServerTasks-1649` (`0.0.422`), initially pending/executing. **Wait for its actual terminal verdict**; pending does not count as acceptance. This paragraph is a historical snapshot, not a live task-status feed.
- GitHub `octopus/verify` returned **failure** for #388 (`ServerTasks-1368`) and #390 (`ServerTasks-1371`). Retrieve actual failed step names and raw logs, fix root causes, and rerun the entire exact-SHA process. Neither D1 nor a successful unrelated main SHA repairs these failed builds.
- The existing main release `dbf9fbde52a11bbc069e19bdeca2658d8dcc1147` recorded `octopus/verify=success` on 2026-10-23; that proves only that commit, not this PR or the stacked free-routing branches.
- Required release acceptance remains eight actual Octopus lanes, resulting signed status on the exact commit, reviewed secrets/config inheritance, one-to-one task status continuity, and a rehearsed rollback. Do not use GitHub Actions or a Vercel preview to replace Octopus.

## Tests and hold points

Original PR baseline reported passing the Node built-in test runner with an SQLite-backed fake D1 interface. The subsequent three regressions committed on `94f73285` require a fresh `node --test` run and exact-SHA Octopus result before merge. A focused execution of the *committed reconcile function* against fake storage reproduced a previous batch exceeding 50 queries and verified the new 10-task path under that budget (43 in the simulation); this is **not** the full Node suite.

Baseline tests cover Tests cover upsert, expiration, pruning, stable cursor pagination, bad input, explicit backend selection, real reconciler transition to GitHub + terminal deletion, and both existing webhook/HMAC and KV backwards compatibility. Production migration and Octopus task logs are independent gates.

**Important:** Both P1 #388 and P2 #390 have genuine Octopus `failure` verdicts. P3a #393 received `error` due to KV daily-write exhaustion. Do not override those with client-side or synthetic success or assume D1 fixes the Octopus worker test failures.
