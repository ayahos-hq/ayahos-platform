# Render service inventory

This is the human-readable companion to the machine-readable canonical inventory at
`deploy/service-inventory.json`. CI validates that the Render blueprint does not drift
from that inventory.

The inventory's release contract requires `make release-check` with real PostgreSQL and
`ruby scripts/live_release_smoke.rb` with a current runtime key. Their outputs belong in the
release evidence template; health-only probes never satisfy the functional release checks.

## Keep

- `goblin-dual-lineage-api`: lightweight governed FastAPI control plane and Supabase evidence writer. It does not host model weights, provider runtimes, or ML packages.
- `goblin-dual-lineage-web-live`: canonical internal operator/admin Next.js surface. The live service runs with the `admin` deployment role, redirects `/` to `/control`, and remains noindex/nofollow.
- Supabase project `supabase-copper-island`: canonical operational-evidence Postgres store.
- External inference targets are separate and independently operated: Node 1 (`node-001`), the Oracle cloud server (`oracle-heavy`), and AWS Bedrock.

## Public Vercel surface

- Vercel project `goblinos-dual-lineage` is the canonical public/customer-facing surface and deploys `apps/site`. It is linked to this GitHub repository and deploys `main` to production automatically, with preview deployments for pull requests (verified 2026-10-14; see [`evidence-2026-10-14.md`](evidence-2026-10-14.md)).
- The production root was live-verified with HTTP 200 and public product metadata.
- `/control` and `/nodes` are absent from that deployment and return HTTP 404.
- The public Vercel project uses a distinct server-side `GOBLIN_SITE_API_KEY` to authenticate its same-origin chat proxy to Render; it is never exposed to browser code.
- Runtime cognition, nodes, control, reviewer access, and operator credentials remain on the Render-side internal surface.

## Governed external bridges

- `oracle-cloud-control-mcp`: tracks `main`; bearer auth mandatory; read-only by default; instance writes require operator enablement and explicit confirmation.
- `siliconflow-chatgpt-mcp`: tracks `main`; bearer auth mandatory; credit spending disabled by default and governed by the Action Gateway.

## Retired experiments

These services are obsolete and must not receive traffic or new secrets. Their names are
retained only in the versioned inventory and rejection/audit checks:

- `goblin-dual-lineage-overmind-tiny`
- `goblin-dual-lineage-overmind-fast`
- `goblin-dual-lineage-overmind-stable`
- `goblin-dual-lineage-overmind-portable`
- `goblin-dual-lineage-overmind-live`
- `goblin-dual-lineage-overmind`
- `goblin-dual-lineage-overmind-cpu`
- `goblin-dual-lineage-web`
- `goblin-dual-heritage-undermind`

The Render connector available to this project does not expose service deletion or branch changes.
Until those resources are retired in the Render dashboard, treat them as unverified external state:
the canonical blueprint declares none of them, and the API rejects retired Render Overmind URLs.

## Runtime invariants

- Render has no canonical Overmind URL or model alias. It authorizes requests, dispatches to registered external targets, and records governed evidence. The provider factory rejects retired Render Overmind endpoints rather than routing to them.
- Node 1 (`node-001`), the Oracle server (`oracle-heavy`), and AWS Bedrock are separate targets with independent credentials, health, and capacity.
- The 90-second dispatch budget applies only when the selected external target advertises and supports it.
- Runtime, operator, browser reviewer-access, database, Datadog, and provider credentials are `sync: false` secrets. Blueprint/code changes must never regenerate them.
- `DUAL_LINEAGE_RUNTIME_API_KEY` authenticates internal/operator callers; `DUAL_LINEAGE_SITE_API_KEY` is a separate credential for the Vercel public-chat proxy.
- The web proxy reuses the runtime API key for internal review calls, eliminating the old duplicated review-secret drift.
- Smoke request IDs use reserved prefixes and smoke labels never count as human-review evidence.
- Human promotion evidence remains text-free and consented.
- The current live audit records the canonical API, operator web, Oracle bridge, and SiliconFlow bridge separately. Re-run the deployment audit after any branch, blueprint, or provider change; the machine-readable inventory is authoritative for declared services.
- Governed external actions emit sanitized metadata-only audit logs and bridge files are included in CI linting.
