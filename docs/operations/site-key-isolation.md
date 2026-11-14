## Independent site credentials

The Render control plane can accept an optional DUAL_LINEAGE_SITE_API_KEY_SECONDARY
in addition to its existing DUAL_LINEAGE_SITE_API_KEY. Both keys authorize
/v1/cognition and /v1/rate-limit/public, but neither grants operator privileges.
Assign this optional secondary key only to the Vercel site's
GOBLIN_SITE_API_KEY, preserving the Cloudflare Pages credential and runtime key.

Rollout: deploy the additive auth code; configure the same high-entropy secondary
secret in Render and Vercel using protected environments; redeploy only the
Vercel production project; verify both Cloudflare and Vercel public chat, a
wrong-key 403, and continued Node 001 heartbeats. Do not commit secret values.