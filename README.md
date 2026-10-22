# AyahOS Platform — provisional source extraction

**Status: private, un-deployed, not production authority.** This repository is a staging home for CI/CD orchestration, Octopus project definitions, deployment templates, release checks and infrastructure records. Do not connect Octopus, GitHub webhooks, Cloudflare or any production service to this repo until the migration gates are complete.

## Pinned import

- Original: `fuaadabdullah/AyahOS_Dual_Lineage` at `df20951d3ba7e8e58effb4c06b699322739e28a5`.
- **50 source blobs** copied exactly with original executable modes under `.octopus/`, `deploy/`, `scripts/ci/`, `docs/infrastructure/`; LICENSE and NOTICE carried over.
- Source file identities and Git modes are recorded in `SOURCE-PROVENANCE.json`.
- This snapshot **retains legacy monorepo-relative script paths and service references**; it is not a deployable multi-repo pipeline.
- Existing Cloudflare Pages and Vercel rollback remain unchanged; Overmind/Undermind/Spine authority stays in the source backend.

## Safe independent checks

From this repository:
```sh
python3 scripts/verify-platform.py
node --test deploy/octopus-github-bridge/test/worker.test.js
find scripts/ci -type f -name '*.sh' -exec bash -n '{}' \;
```
These inspect source identity, CI topology and the webhook bridge's local mocked behavior. They do **not** create Octopus releases, connect to GitHub status APIs, deploy containers, load secrets, test PostgreSQL, or certify the source's complete eight-lane Octopus runtime. That remains a separate authenticated integration/release gate.

The upstream `deploy/octopus-github-bridge/wrangler.jsonc` still targets the original monorepo; **do not run `wrangler deploy` from here.** Even if documentation describes an existing deployed Worker, that refers to an earlier service configuration, not deployment from this new repository.

See `MIGRATION-GATES.md` and master [migration issue #243](https://github.com/fuaadabdullah/AyahOS_Dual_Lineage/issues/243).
