# Model Reconciler

A separate narrow Cron Worker that monitors Node 001 health.

## Purpose

Fetches node heartbeats from Core API (`/v1/compute/nodes`) every 5 minutes and:
- Marks nodes as stale after 300s
- Flags nodes as offline when unreachable
- Tracks consecutive failure counts
- Reports brain role coverage
- Alerts on zero-healthy-node roles

## Deployment

```bash
npx wrangler deploy --name=model-reconciler
```

Production environment uses `CORE_API_KEY` from Wrangler secrets.

## Endpoints

- `GET /v1/compute/nodes` — Core API (authenticated)
- Cron: `*/5 * * * *` — runs every 5 minutes

## Testing

```bash
npx wrangler tail --live
```

## Secrets

Set in Cloudflare Dashboard or Wrangler:
- `CORE_API_KEY` — for Core API authentication
