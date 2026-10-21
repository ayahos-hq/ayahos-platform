# Deployment audit — 2026-09-30

This is a point-in-time external audit recorded separately from the versioned
deployment contract. Secret values were not read or recorded.

| Service | Branch | Observed live commit | Endpoint | Observed state |
| --- | --- | --- | --- | --- |
| `goblin-dual-lineage-api` | `main` | `76d3b1b637a3626c5f222865d437f477319855c` | `https://goblin-dual-lineage-api.onrender.com` | live; deploy `dep-daumt9k9v7es73be37sg` |
| `goblin-dual-lineage-web-live` | `main` | `76d3b1b637a3626c5f222865d437f477319855c` | `https://goblin-dual-lineage-web-live.onrender.com` | live; deploy `dep-daumt9k9v7es73be37e0` |
| `oracle-cloud-control-mcp` | `main` | `76d3b1b637a3626c5f222865d437f477319855c` | `https://oracle-cloud-control-mcp.onrender.com` | live; deploy `dep-daumt9k9v7es73be37l0` |
| `siliconflow-chatgpt-mcp` | `main` | `76d3b1b637a3626c5f222865d437f477319855c` | `https://siliconflow-chatgpt-mcp.onrender.com` | live; deploy `dep-daumt9c9v7es73be3730` |

The canonical blueprint now declares only the API and operator web services,
both explicitly on `main`, with `/health` and `/api/build` health paths. The
active Render services now report those same health paths, and the live
endpoints returned HTTP 200 at each configured path during this audit.

The old Overmind/model and heritage services remain physically present but are
suspended, have their environment replaced with `RETIRED_SERVICE=true`, and
are excluded from `render.yaml` and the canonical inventory. The API runtime
no longer configures an Overmind Render URL and rejects retired Render
Overmind endpoints if supplied through an external environment.
