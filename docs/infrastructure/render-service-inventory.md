# Render service inventory

This is the human-readable companion to the machine-readable canonical inventory at
`deploy/service-inventory.json`. CI validates that the Render blueprint does not drift
from that inventory.

The inventory's release contract requires `make release-check` with real PostgreSQL and
`ruby scripts/live_release_smoke.rb` with a current runtime key. Their outputs belong in the
release evidence template; health-only probes never satisfy the functional release checks.

## Production auto-deploy release gate (verified 2026-10-24)

After auditing the owner-confirmed Render **My Workspace**, all four active AyahOS services were observed running monorepo SHA `06be207dce6422124f22c77d0f507aac937babda` while GitHub `octopus/verify` was still pending. Render had `autoDeployTrigger: commit`, so a successful Render build and deployment did **not** prove an Octopus-approved release.

Using the authenticated Render CLI on an authorized operator workstation, the following existing services were set to `autoDeployTrigger: off` without changing service images, environment secrets, branches, domains, or traffic:

- `goblin-dual-lineage-api` (`srv-dasd3ajbc2fs73eos5jg`)
- `goblin-dual-lineage-web-live` (`srv-dasd4j3bc2fs73ep19sg`)
- `oracle-cloud-control-mcp` (`srv-dasdqgm0tbcc73evq5hg`)
- `siliconflow-chatgpt-mcp` (`srv-dasfgm17lnhs738vcvt0`)

A fresh Render API readback independently confirmed each service is `autoDeploy=no` and `autoDeployTrigger=off`. Immediately afterward, all four retained live deployment status at SHA `06be207dce`. Two canonical service definitions in this blueprint are pinned to `autoDeployTrigger: 'off'` to resist configuration drift. The two MCP bridges are configured outside `render.yaml`; keep their live service setting off separately until a reviewed IaC owner is assigned. Suspended retired services were left untouched.

**Operator release process:** Run Octopus against the **exact SHA** and inspect all required step outcomes. Confirm encrypted recovery/restorability and data migration compatibility. Manually deploy only an approved SHA with a rollback plan, then verify deployed build identity, authenticated runtime behavior, and redacted telemetry. A generic `/health` HTTP 200 or successful Render build is insufficient to authorize a release. Do not re-enable on-commit auto-deploy or treat the Vercel rollback's frozen SHA as source drift.

## Keep

- `goblin-dual-lineage-api`: lightweight governed FastAPI control plane and Supabase evidence writer. It does not host model weights, provider runtimes, or ML packages.
- `goblin-dual-lineage-web-live`: canonical internal operator/admin Next.js surface. The live service runs with the `admin` deployment role, redirects `/` to `/control`, and remains noindex/nofollow.
- Supabase project `supabase-copper-island`: canonical operational-evidence Postgres store.
- External inference targets are separate and independently operated: Node 1 (`node-001`), the Oracle cloud server (`oracle-heavy`), and AWS Bedrock.

## Public Cloudflare surface and frozen Vercel rollback

- **Primary:** Cloudflare Pages project `ayahos`, sourced from the original monorepo's `apps/site` on `main`, serves `https://ayahos.pages.dev`. The static Next.js export and Pages Functions own customer-facing same-origin API routes. The exact deployed SHA and authenticated chat must be checked per release rather than inferred from a successful build.
- **Rollback only:** Vercel project `goblinos-dual-lineage` at `https://ayahos.vercel.app` is intentionally frozen. `/backup` on the Cloudflare primary leads to this fallback; a frozen rollback SHA is not drift to fix by auto-deploying Vercel.
- Site Functions use a distinct server-side `GOBLIN_SITE_API_KEY` for the governed Render chat proxy; browser JavaScript must not receive it. No production secrets are copied to previews or provisional repositories.
- Operator/runtime cognition, nodes, control, reviewer access and credentials stay behind the separate Render-side internal authority. Neither the public primary nor the fallback may expose `/control` or `/nodes`.
- Historical 2026-10-14 Vercel evidence remains in [the dated report](evidence-2026-10-14.md) but does **not** supersede the current primary/rollback designation in `deploy/service-inventory.json`.

## Governed external bridges

- `oracle-cloud-control-mcp`: tracks `main`; bearer auth mandatory; read-only by default; instance writes require operator enablement and explicit confirmation.
- `siliconflow-chatgpt-mcp`: tracks `main`; bearer auth mandatory; credit spending disabled by default and governed by the Action Gateway.

### Bridge-only RAG startup preflight

Both bridges import `dual_lineage.runtime.runtime_coordinator` to obtain the deterministic Undermind, Shared Spine, and Action Gateway context. The shared runtime defaults `DUAL_LINEAGE_RAG_ENABLED` to `true`, which requires `DUAL_LINEAGE_RAG_URL` and `DUAL_LINEAGE_RAG_SERVICE_TOKEN`. These standalone bridges do **not** host the Ruby RAG sidecar. On their own Render services, explicitly set **`DUAL_LINEAGE_RAG_ENABLED=false`** as a non-secret service-scoped environment setting. Do not turn RAG off for the canonical `goblin-dual-lineage-api`; that service has its own Ruby RAG sidecar and retrieval contract. This setting disables only the bridge's unnecessary retrieval backend. It does not authorize writes, bypass deterministic Undermind decisions, or change confirmation requirements.

The Oracle bridge repeatedly failed startup with `ValueError: DUAL_LINEAGE_RAG_URL is required for the ruby backend` and Render exit code 3 on October 22–23, 2026. The Oracle **service-only** setting was installed on 2026-10-23 and a new deployment of `a7ef41fe` reached Render `live` at 00:54 UTC after application startup and `/health` 200 responses. Health verifies boot, **not** authenticated MCP tools or an OCI action. The SiliconFlow bridge uses the same runtime import: independently verify its live environment and startup, and do not assume Oracle configuration propagates to it.

Post-deploy checks: read Render build identity, inspect startup logs for `Application startup complete` and `/health` 200, confirm no `DUAL_LINEAGE_RAG_URL` startup exception, then test authenticated read-only bridge status. Writes and spend controls must remain disabled unless separately approved. The bridge's Shared Spine persistence mode must be audited separately; a healthy boot is not proof that its event records are durable. Keep non-secret bridge settings in the service inventory checklist to avoid silent dashboard-only drift. On rollback, restore the previous healthy image **without** re-enabling RAG on a standalone bridge.

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
- `DUAL_LINEAGE_RUNTIME_API_KEY` authenticates internal/operator callers; `DUAL_LINEAGE_SITE_API_KEY` is a separate credential for the Cloudflare Pages Functions public-chat proxy (and the separately frozen Vercel rollback, when used).
- The web proxy reuses the runtime API key for internal review calls, eliminating the old duplicated review-secret drift.
- Smoke request IDs use reserved prefixes and smoke labels never count as human-review evidence.
- Human promotion evidence remains text-free and consented.
- The current live audit records the canonical API, operator web, Oracle bridge, and SiliconFlow bridge separately. Re-run the deployment audit after any branch, blueprint, or provider change; the machine-readable inventory is authoritative for declared services.
- Governed external actions emit sanitized metadata-only audit logs and bridge files are included in CI linting.
