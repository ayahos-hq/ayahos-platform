# Rate Limiting

AyahOS Dual-Lineage uses one PostgreSQL-backed shared rate-limit layer for the
public proxy and the internal runtime. A bounded in-process limiter remains
available only for explicitly local mode; deployed Render API instances use
the shared store, and the public site's `/api/chat` Pages Function checks the
authenticated public endpoint before calling cognition.

## Public chat

The `/api/chat` Pages Function (`apps/site/functions/api/chat.ts`) sends a one-way
client token to `POST /v1/rate-limit/public` before parsing the body or calling
cognition. The Render endpoint authenticates the site credential and atomically
increments the public bucket in PostgreSQL. The raw forwarded IP never leaves
Cloudflare.

Defaults:

- 10 requests per minute per client, enforced in the shared database,
- client identity uses Cloudflare's `CF-Connecting-IP` header first (set at the edge and overwritten on every request),
- raw user-agent values and IP addresses are never sent to Render.

A blocked request returns HTTP 429 with `Retry-After`, `RateLimit-Limit`, `RateLimit-Remaining`, and `RateLimit-Reset`.

## Runtime API

FastAPI applies shared route-class limits before endpoint authentication/processing:

- cognition: 30 requests per 60-second window,
- authenticated operators: 60 requests per window,
- provider-cost exposure: 30 requests per window,
- repeated failures: 5 failures per window,
- mutations: 120 per window,
- reads: 600 per window,
- compute-node heartbeat: 240 per window.

`/health` is exempt so deployment probes continue to work during abuse.

Authenticated requests are keyed by a one-way hash of the presented credential, never by the raw secret. Unauthenticated requests use the direct socket client address. `X-Forwarded-For` is ignored unless `DUAL_LINEAGE_RATE_LIMIT_TRUST_FORWARDED_FOR=true`; do not enable that unless the API is reachable only through a trusted reverse proxy.

The PostgreSQL bucket key includes the policy, a one-way principal hash, and
the fixed-window epoch. `INSERT ... ON CONFLICT DO UPDATE` makes increments
atomic across replicas and restarts; expired buckets are removed during checks.

## Configuration

See `.env.example` for:

- `DUAL_LINEAGE_RATE_LIMIT_*`
- `PUBLIC_CHAT_RATE_LIMIT_*`
- `DUAL_LINEAGE_PUBLIC_RATE_LIMIT_URL`

Datadog receives only a bounded-cardinality `http.rate_limited` count tagged by route class. Client identifiers and credentials are not exported.

## Deployment note

Application limits are defense in depth. The public site should also use a
Cloudflare WAF rate-limiting rule when available so abusive requests are
rejected before a Pages Function invocation consumes compute. The public client
identity code trusts only `CF-Connecting-IP` when it is present; the API does not
trust generic forwarded headers by default.
