# Cloudflare Pages: public site

Status as of the 2026-10-21 post-fix smoke: **Cloudflare Pages served PR #195's `5049ab0` build and a single public chat request completed successfully.** The public UI sent `Reply only with OK.` and received `OK` with `done` status, demonstrating a working chat path for that request. This is **not** a complete release gate: full-length SSE, JSON mode, rate limits, cancellation, provider health/failover, and the API's own deployed SHA remain unverified. Newer GitHub merges may temporarily be ahead of live Pages. Vercel last reported fallback build `4999457`; custom-domain traffic cutover was not independently checked. The encrypted credential's value was neither read nor recorded.
See [Live verification log](#live-verification-log) for exactly what was and was not observed.

## What runs where

| Piece | Host | Source |
| --- | --- | --- |
| Customer UI (static) | Cloudflare Pages CDN | `apps/site` → `out/` |
| `POST /api/chat` (SSE, budgets, rate limit, grounding) | Pages Function | `apps/site/functions/api/chat.ts` → `src/server/public-chat.ts` |
| `GET /api/build` (commit identity) | Pages Function | `apps/site/functions/api/build.ts` |
| Overmind, Undermind, Shared Spine, Action Gateway | Render (unchanged) | `apps/api` |

Cloudflare delivers the frontend and runs the thin chat proxy. Model inference, policy decisions, and
execution evidence stay on the Render API. The proxy calls the same `/v1/cognition` and
`/v1/rate-limit/public` endpoints, with the same `X-Dual-Lineage-Key` header, as the Vercel route did.

## Pages project settings (dashboard)

Set these when connecting the repository in Cloudflare Pages. The project name in
`apps/site/wrangler.jsonc` is `ayahos`; change both if a different name is chosen.

- Production branch: `main`. Preview deployments: every other branch.
- Root directory: `apps/site`
- Build command: `cd ../.. && pnpm install --frozen-lockfile && pnpm --filter @goblinos-dual-lineage/site build`
- Build output directory: `out`
- Environment variable `NODE_VERSION`: `22`
- Recommended build variables: `PNPM_VERSION=9.15.9` (the Pages image defaults to pnpm 10, while the
  repo pins `packageManager: pnpm@9.15.9`) and `SKIP_DEPENDENCY_INSTALL=1` (the build command already
  runs the workspace install, so Pages' automatic install in `apps/site` is redundant). The first
  preview build succeeded with the image defaults, so these are reproducibility and build-time
  hygiene, not observed failures.
- `apps/site/wrangler.jsonc` is the source of truth for the compatibility date, flags, and the
  non-secret public rate-limit URL. Its `name` must equal the Pages project name. The site key and
  any other credentials remain encrypted Pages secrets; never put them under `vars`. Confirm the
  shared limiter with the 429 check in cutover step 5.

Installing the Cloudflare GitHub integration on `fuaadabdullah/AyahOS_Dual_Lineage` is a dashboard
step that only a repository owner can complete.

## Environment and secrets

Set each secret as **Encrypted** in the **Production** environment only. Never commit values. Preview
deployments run the code of whatever branch was pushed, so they must not hold the production site key
(see "Preview" below).

| Name | Type | Required | Notes |
| --- | --- | --- | --- |
| `GOBLIN_SITE_API_KEY` | secret | yes (Production) | Must equal `DUAL_LINEAGE_SITE_API_KEY` on the Render API service. The API compares them exactly. |
| `DUAL_LINEAGE_PUBLIC_RATE_LIMIT_URL` | variable | yes (Production) | `https://goblin-dual-lineage-api.onrender.com/v1/rate-limit/public`. If unset, the shared limiter is skipped entirely. |
| `TAVILY_API_KEY` | secret | optional | Enables web grounding. Unset means no grounding. |
| `PUBLIC_CHAT_DEADLINE_MS` | variable | optional | Default 270000. Copy any value set on Vercel. |
| `PUBLIC_CHAT_MAX_COST_USD` | variable | optional | Default 0.05. |
| `PUBLIC_CHAT_RATE_LIMIT_PER_MINUTE` | variable | optional | Default 10. Used only by the local fallback limiter. |
| `PUBLIC_CHAT_RATE_LIMIT_MAX_BUCKETS` | variable | optional | Default 5000. |
| `DUAL_LINEAGE_API_BASE_URL` | variable | **leave unset** | Local stub override only. The code honours it only for `http` loopback hosts (`127.0.0.1`, `localhost`, `[::1]`), so it cannot redirect the site key elsewhere. |

Preview: do not set `GOBLIN_SITE_API_KEY` or `TAVILY_API_KEY` in Preview. A preview runs whatever
Function code a pushed branch contains, and preview URLs are public by default, so a key there is
readable by anyone who can push a branch. Chat in Preview then fails closed at the API; this was
observed on 2026-10-20 as `503 PROVIDER_UNAVAILABLE` with cost 0. To exercise authenticated chat
before cutover, either verify on the Production deployment after merge while customers are still on
Vercel, or put previews behind Cloudflare Access, set a key temporarily, and remove it afterwards.

Production must also set `DUAL_LINEAGE_PUBLIC_RATE_LIMIT_URL`. When it is unset the shared limiter is
skipped and no public limit applies at all (this is inherited from the Vercel route).

Vercel values cannot be read from this environment (the project env list returns 403), so copy the
existing values from the Vercel dashboard into the Pages settings by hand.

## Security headers

`apps/site/public/_headers` sets a Content-Security-Policy, HSTS, `X-Frame-Options: DENY`,
`nosniff`, a strict Referrer-Policy, and a Permissions-Policy for static assets. Function responses set
`nosniff`, `Referrer-Policy: no-referrer`, and `Cache-Control: no-store` in
`src/server/api-response.ts`. `script-src` and `style-src` allow `'unsafe-inline'` because Next's
static export emits inline bootstrap scripts; tightening this needs hash or nonce support first.
Cloudflare Web Analytics can inject a beacon script, which this CSP would block; leave that off or
allow its origin.

## Build identity

`scripts/write-build-info.mjs` runs before every build and writes `src/generated/build-info.ts`
from `CF_PAGES_COMMIT_SHA` and `CF_PAGES_BRANCH`. Functions read that file, so `/api/build` reports
the commit that was built. Outside Pages it falls back to `git` and reports `deployment_platform:
"local"`.

Check a deployment:

```bash
curl -sS https://<pages-url>/api/build
# expect build_sha = the deployed commit, source_branch = main, deployment_platform = cloudflare-pages
```

## Local verification

```bash
pnpm install --frozen-lockfile
pnpm --filter @goblinos-dual-lineage/site build
# write apps/site/.dev.vars (gitignored) pointing DUAL_LINEAGE_API_BASE_URL at a local stub
pnpm --filter @goblinos-dual-lineage/site dev:pages
```

This gives `verified-local` evidence only. It runs the static output and Functions in `workerd`, with
an upstream stub that enforces the key header and emits SSE. It does not prove Cloudflare production
behaviour or the live Render path.

## Cutover

Customers are not switched yet. Steps and their state:

1. Connect the repository to a Pages project. **Done** (2026-10-20; the first preview build of
   `6d92912` succeeded).
2. Verify a Preview deployment: build identity, headers, and routing are verified; chat needs a key
   (see "Preview" above), so it is verified on Production in step 5.
3. Decide the customer URL. **Open.** Today it is `ayahos.vercel.app`; the Pages URL is
   `ayahos.pages.dev` unless a custom domain is attached.
4. Pause Vercel production builds of `main`. **Done in the repo:** `apps/site/vercel.json` sets an
   `ignoreCommand` that skips builds of `main`, so Vercel keeps serving its last production
   deployment (the previous Next.js build, with working chat). Without it, merging would make the
   Vercel build static with no `/api/chat`. Delete the file only after customers have moved.
5. Merge. Cloudflare then builds Production from `main`. Set the Production secrets and variables
   above, redeploy, and verify chat on `https://ayahos.pages.dev`: a JSON answer, a streamed answer,
   a 429 under load, `/api/build` equal to the merged commit, a full-length streamed answer (watch
   for Cloudflare error 1102, see the CPU note below), and the early-disconnect check described under
   "Client-disconnect cancellation".
6. Switch customers, then change the `https://ayahos.vercel.app` defaults in
   `scripts/verify_public_site.sh`, `scripts/public_chat_smoke.rb`, `scripts/live_release_smoke.rb`,
   and `deploy/service-inventory.json` to the new URL, and run `scripts/verify_public_site.sh` against
   it. CircleCI and Codefresh are retired, so there is no automatic public-site job to update; that
   script is run by hand. Until the defaults change, running these scripts against
   `ayahos.vercel.app` compares its frozen build SHA with new merges and will not match.
7. Keep the Vercel project and its previous production deployments for rollback. Do not delete them
   until Cloudflare has run cleanly in production for an agreed period.

## Vercel rollback redirect

Cloudflare Pages remains the **primary** public site at `https://ayahos.pages.dev`.
The existing, intentionally frozen Vercel deployment remains a **separate rollback** at
`https://ayahos.vercel.app`; do not redirect Vercel back to Cloudflare or delete its
working chat deployment.

`GET https://ayahos.pages.dev/backup` is a **temporary 302** Pages static
redirect (defined in `apps/site/public/_redirects`) to the fixed Vercel origin.
The public chat offers **Use Vercel backup** after HTTP 502/503/504 or a network
failure. This switch is user-controlled, not an automatic retry or auto-redirect.
The UI's backup link contains no message content, tokens, or query parameters;
it does not replay the failed request. Never put sensitive content in a manually
constructed `/backup` URL: static redirects may preserve query parameters.
Browser conversation history belongs to the originating site and does **not**
automatically migrate to Vercel.

**Boundary:** This protects against problems with the Cloudflare-hosted app or
chat Function while the Pages redirect itself is reachable. A complete Cloudflare
DNS/edge/Pages outage cannot serve its own 302, and both frontends still depend
on the same Render cognition API. The independently accessible backup URL is
`https://ayahos.vercel.app`. For *automatic full-site failover* on a
custom customer domain, separately configure and test an independent health-checked
traffic director / DNS failover with a primary and secondary endpoint. No such
custom-domain failover or DNS change is claimed here.

Rollback drills should separately verify (1) Cloudflare `/api/build`,
(2) temporary `/backup` redirect Location and 302 status, (3) direct Vercel
`/api/build`, and (4) one bounded Vercel chat round-trip, keeping all secrets
out of checks and logs. A passing redirect alone is not proof the Vercel
chat backend works.

## Rollback

- Customers stay on, or return to, the Vercel URL. Vercel's production deployment is unchanged while
  the `ignoreCommand` is in place.
- To resume Vercel builds, delete `apps/site/vercel.json`, and only after restoring a Vercel-compatible
  build (the static export has no `/api/chat` there).

## Live verification log

Smoke-level evidence from the Cloudflare preview. This is not a full end-to-end proof.

| When (UTC) | Target | Commit | Request | Observed |
| --- | --- | --- | --- | --- |
| 2026-10-20 about 12:30 | `https://migrate-site-cloudflare-page.ayahos.pages.dev` | `6d92912` | `GET /` | 200 through Cloudflare, with CSP, HSTS, `X-Frame-Options: DENY`, `nosniff`, referrer and permissions policies |
| same | same | same | `GET /api/build` | `build_sha` equal to `6d92912…`, `source_branch` `migrate/site-cloudflare-pages`, `deployment_platform` `cloudflare-pages`, `no-store` |
| same | same | same | `GET /api/chat` | 404 |
| same | same | same | `POST /api/chat` (JSON) | 503 `PROVIDER_UNAVAILABLE`, cost 0, about 150 ms to Render. Render answers a keyless request with 401, so the preview had no usable site key. Authenticated chat is **not** verified |
| same | same | same | `POST /api/chat` (SSE) | 200 `text/event-stream` with an empty body. Render's stream endpoint answers a missing or bad key with HTTP 200 and a JSON body that is not SSE, so the stream verifier ends the stream. The same code path existed in the Vercel route |
| 2026-10-20 about 20:35 | same | `c6696b4` | Pages build and deploy | Succeeded with `compatibility_flags` `["nodejs_compat", "enable_request_signal"]`; `/api/build` reports `c6696b4…` |
| same | same | same | `GET /api/chat` | 405 JSON `METHOD_NOT_ALLOWED` with `Allow: POST` |
| same | same | same | `HEAD /api/build` | 200 `application/json`, `no-store` |
| same | same | same | `POST /api/chat` with a 200 KB chunked body (no `Content-Length`), and with a declared-length 200 KB body | 413 `REQUEST_TOO_LARGE` for both |
| same | same | same | `POST /api/chat` invalid JSON; invalid role | 400 `INVALID_JSON`; 400 `INVALID_MESSAGES` |
| same | same | same | `POST /api/chat` valid, no site key | 503 `PROVIDER_UNAVAILABLE`, `retryable: true`, `spent_usd` 0 |
| same | same | same | `GET /api/build` with different User-Agents | `Python-urllib/3.12`: 403 (error 1010). `curl`, a browser agent, and `AyahOS-live-smoke/1`: 200. The smoke scripts now send the last one |
| 2026-10-20 about 20:40 | `https://ayahos.pages.dev` | `a40c30c` | `GET /api/build` | 200; `build_sha` equals `a40c30c…`, `source_branch` `main`, `deployment_platform` `cloudflare-pages`, `no-store` |
| same | same | same | `POST /api/chat` valid JSON | 503 `PROVIDER_UNAVAILABLE`, `spent_usd` 0; the public rate-limit URL is deployed from Wrangler, but Production still has no encrypted `GOBLIN_SITE_API_KEY`. Authenticated chat remains **not verified** |

### 2026-10-21 deployment verification refresh

**Later same-day follow-up:** The Pages and Render operator `/api/build` endpoints both returned `5049ab0adb8a4728d362f7b1716873ea84d6d0ca`. In a subsequent one-message browser smoke against `https://ayahos.pages.dev`, the UI returned `OK` marked `done` for `Reply only with OK.`, without a visible authentication/configuration error. This verifies the simple live chat path at that deployed SHA; it does not establish the cause of the earlier transient page-load error or prove all chat modes.



| Scope | Live observation | Evidence level |
| --- | --- | --- |
| Cloudflare Pages `https://ayahos.pages.dev/api/build` | `build_sha=60c18aefe57688427defabb645547371cb06cf87`, `source_branch=main`, `deployment_platform=cloudflare-pages` | verified-live for **that SHA**, not for later merges |
| Render operator `https://goblin-dual-lineage-web-live.onrender.com/api/build` | `build_sha=60c18aefe57688427defabb645547371cb06cf87` | verified-live operator build identity at observation |
| Vercel fallback `https://ayahos.vercel.app/api/build` | `build_sha=49994571435b9a1e89232c38f37689a934a75f91` | verified-live frozen fallback identity at observation |
| Render API `/health` | `status=ok`, `service=ayahos-control-ruby`, `core=healthy` | verified-live health only; API build SHA and authenticated cognition not proven |
| Cloudflare public chat | One browser message (`Reply only with OK.`) showed Thinking, no completed answer, then a generic page-load error | failed smoke; failure origin and current secret binding remain unverified |
| PR #195 (`5049ab0`) | Pages `/api/build` subsequently matched `5049ab0`; the missing-key and invalid-SSE error-path fix was served | verified-live for build identity; no full error-path runtime probe |

**Remaining release gates:** A single Cloudflare UI chat request succeeded after #195 deployed, so do not keep describing all chat as broken. Verify current Pages SHA again after newer merges, execute authenticated JSON mode, long SSE, rate limiting, cancellation and trace/usage checks, and confirm the Render API revision. Keep Cloudflare Production credentials encrypted; do not paste or commit site keys. The 2026-10-20 log above describes historical failures.

## Known limits and follow-ups

- **Workers plan and CPU time.** Pages Functions run under Workers CPU limits: 10 ms per request on
  the Free plan, 30 s by default on Workers Paid. Time spent waiting on Render or Tavily is not
  counted, but the proxy re-parses and re-encodes every SSE frame. Measured on Node/V8 on
  2026-10-20: about 1.4 ms for a 200-frame answer and about 15 to 40 ms for a 2,048-frame answer
  (one frame per token, the maximum length). Short answers fit the Free limit; long answers are likely
  to exceed it and fail with Cloudflare error 1102. Use Workers Paid for production, or measure a
  full-length answer on the Production deployment (step 5) before moving customers.

- Cloudflare is steering new projects toward Workers with static assets. Pages Functions remain
  supported. Moving to Workers is a later decision and is not part of this change.
- **Client-disconnect cancellation.** The former Vercel route set `supportsCancellation`; its Cloudflare
  equivalent is the `enable_request_signal` compatibility flag, which is opt-in on Workers and is set
  in `apps/site/wrangler.jsonc`. On the streaming path a disconnect is detected on the next write to the
  client (verified-local: the upstream closed about 1.5 s after the client left, with runtime
  heartbeats flowing). Upstream heartbeats default to 15 s (`DUAL_LINEAGE_SSE_HEARTBEAT_SECONDS`), so
  generation can run up to about that long past a disconnect. **Not verified:** that `request.signal`
  fires on a disconnect before the first byte (Tavily, runtime preflight, non-streaming answers). In
  local `wrangler pages dev` and in bare `workerd`, with the flag off and on, the upstream stayed open
  for the full duration, so local runs cannot show it. Check on Production: start a non-streaming and a
  streaming chat, drop the connection after 2 s, and confirm on Render that the request was
  interrupted and the spend stayed near zero.
- The in-isolate fallback limiter is per isolate, so it is only a backstop. The shared limiter on
  Render is the real enforcement.
- Client identity now uses `CF-Connecting-IP`. The site never trusts `x-vercel-forwarded-for`
  after cutover.
