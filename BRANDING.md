# AyahOS product identity and legacy-name migration contract

**Canonical product naming (effective November 13, 2026)**

| Role | Current external name | Description |
| --- | --- | --- |
| Platform/ecosystem | **AyahOS** | User experience, services and infrastructure |
| Conversational AI assistant | **Ayah** | The assistant users message and see in transcripts |
| Operator application | **AyahOS Operator Console** | Restricted operator controls and observability |
| Reasoning architecture | Overmind, Undermind, Shared Spine | Internal cognitive components, not the assistant's product name |
| Runtime and governance | AyahOS Core / AyahOS Platform | Component owner and deployment surfaces |
| Compute | AyahOS Workloads | Execution workers, isolated runtime and compute |

**Goblin / GoblinOS are historical product names, not active user-facing branding.** Avoid introducing them in new headings, chat labels, installable-app names, onboarding, SEO, accessible product labels, or release announcements. The names of the independently-owned repositories remain `ayahos-site`, `ayahos-core`, `ayahos-admin`, `ayahos-platform`, and `ayahos-workloads`.

## Legacy technical identifiers: preserve until migrated

Historical identifiers remain in source, telemetry and runtime integrations. Renaming them mechanically would cause service outages, lost user preferences, broken CI filters or untrusted release evidence. A reference to one of these identifiers **does not imply the product has reverted to Goblin**.

| Existing identifier class | Representative examples | Migration rule |
| --- | --- | --- |
| Package names and workspace filters | `@goblinos-dual-lineage/site`, `@goblinos-dual-lineage/web`, `@goblinos-dual-lineage/shared` | Update package manifests, lockfiles, importers, build/test scripts and verifier contracts in an atomic, tested compatibility release |
| Secrets and deployment configuration | `GOBLIN_API_KEY`, `GOBLIN_DEPLOYMENT_ROLE`, `NEXT_PUBLIC_GOBLIN_DEPLOYMENT_ROLE` | Inventory all producers and consumers; add backwards-compatible aliases where safe; preserve fail-closed Admin auth; switch producers and consumers together; remove old names only after rollback interval |
| Existing telemetry | `goblin.dual_lineage.*` metric family and historic dashboard queries | Define new `ayahos.*` names and mapping; preserve historical visibility; verify ingestion, cost, dashboards, no-data alerts and counter consistency before deprecating old names |
| Local browser storage | `goblin-theme` and other user-visible state keys | Migrate via read-old/write-new dual compatibility or an explicit one-time migration; do not discard conversation history or settings |
| Source and production identities | `fuaadabdullah/AyahOS_Dual_Lineage`, legacy service names, provenance manifests and pinned hashes | Preserve immutable source history and active production references until an explicit exact-SHA cutover with tested rollback; never rewrite historical attestations or Git history |
| Runtime SDK and API names | Legacy import paths, JSON keys, trace tags, provider names and URL paths | Keep wire/API contracts stable until both endpoints are versioned and contract/E2E tested |

## Acceptance criteria

1. Public UI consistently calls the platform **AyahOS** and the assistant **Ayah**; no Goblin product branding in current UI, metadata, installable-app labels or accessibility surfaces.
2. Operator UI identifies as **AyahOS Operator Console**, remains non-indexed and protected by independent fail-closed authorization.
3. Automated regression tests cover the current user-facing names; inspect social preview images and icons manually before a live cutover.
4. Historical names remain searchable in provenance, telemetry and migration documentation with explicit compatibility context. Do not falsify old reports by renaming historical evidence.
5. Changes that affect authentication, package resolution, model routing, storage, metrics, CI, webhook status, infrastructure, or costs require isolated before/after tests and a reversible release.
6. HQ releases remain **HOLD** until the existing `octopus/hq-operator-verified` exact-commit gate and cross-repository acceptance pass. A branding patch never authorizes a deployment.

## Initial implementation tracking

- Public chat and metadata naming: [Site PR #36](https://github.com/ayahos-hq/ayahos-site/pull/36).
- Operator chrome and app metadata naming: [Admin PR #28](https://github.com/ayahos-hq/ayahos-admin/pull/28).
- Technical identifier migration is a **separate compatibility project**, not an implicit side effect of these branding PRs.

This document sets intended naming and safety boundaries; it is not evidence that the live production surfaces have been migrated.
