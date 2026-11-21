# Oracle Render MCP retirement — live operations record

**Status:** Physically deleted and independently verified on 2026-11-20 (UTC). This is a current operational observation, not a change to the frozen source import.

## Exact decommissioned resource

- Name: `oracle-cloud-control-mcp`
- Render service ID: `srv-dasdqgm0tbcc73evq5hg`
- Former endpoint: `https://oracle-cloud-control-mcp.onrender.com`
- Workspace: `My Workspace` (`tea-d4kf1i0gjchc73a4o3p0`)
- Source was the archived `fuaadabdullah/AyahOS_Dual_Lineage` repository.
- Before deletion, Render reported this service `suspended` with HTTP 503, not active.

## Completed authorized action and evidence

1. An authenticated Render CLI `render services delete srv-dasdqgm0tbcc73evq5hg` dry run identified the exact name, ID, and workspace.
2. The user explicitly authorized deletion. The authorized desktop executed `render services delete srv-dasdqgm0tbcc73evq5hg --confirm --output json`.
3. Independent post-deletion checks: Render's service API returned HTTP 404 / not found; the CLI reported `No service with ID 'srv-dasdqgm0tbcc73evq5hg'`.
4. A fresh authenticated Render inventory reported 13 remaining services, versus 14 before deletion. None of the other 13 listed service IDs were removed.

This evidence demonstrates physical deletion of this one legacy service. It does not verify unused credentials are revoked, all historical references are scrubbed, or that an equivalent MCP API is available elsewhere.

## Preserved services

- The Oracle cognitive node health endpoint `https://oracle-129.213.50.249.nip.io/health` and Node-001 control health endpoint `https://129.213.50.249.nip.io/health` were independently reprobed and each returned HTTP 200 after the deletion.
- The two HTTPS node health endpoints do **not** replace the removed Render `/mcp` service API.
- All other Render services were left untouched.
- No Oracle/Fly runtime configuration, secrets, deployment authority, or feature flags were changed.

## Provenance boundary

The repository's `deploy/service-inventory.json` and `docs/infrastructure/render-service-inventory.md` are **immutable, historical extraction artifacts**, pinned to exact Git blobs in `SOURCE-PROVENANCE.json`. Their old references to this former Render service are **not live inventory assertions**. Do not edit these blobs or simply update their recorded hashes to make CI pass.

This root-level operational record supersedes only the archived inventory's claim about the **one deleted service**. Further live infrastructure state must be reverified with provider APIs. PR #66 intentionally does not promote a new effective deployment inventory or alter pinned source-of-truth release boundaries.

## Integration and release policy

- Inspect live consumers before reintroducing any Oracle MCP integration. Never silently substitute a compute health endpoint for an authenticated MCP action route.
- Follow Octopus operator verification and existing merge/review policies for this documentation-only change.
