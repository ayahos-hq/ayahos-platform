# Zero-cost routing: Cloudflare AI Gateway for Undermind

**Status, October 21, 2026 (verified Cloudflare API):** The owner-authorized Cloudflare account hosting `ayahos.pages.dev` has a real `ayahos-undermind` AI Gateway. A native custom provider `typesafe` exists with `base_url=https://api.typesafe.ai` and `enable=false`. Read-after-write API checks verified `authentication=true`, `byok_only=true`, `collect_logs=false`, `cache_ttl=0`, `zdr=true`, rate limit 10/60 seconds and `retry_max_attempts=1`. Gateway billing auto top-up returned threshold 0 and amount 0; gateway credit balance was 0. **No inference requests were sent.** The gateway configuration exists, but model execution, production runtime wiring, and Octopus end-to-end acceptance are not verified.

## Why Cloudflare, not another gateway service

Cloudflare AI Gateway's basic gateway, caching, metrics and rate limits are free on Workers Free (maximum **10 gateways per account**, as of 2026-10-21). Cloudflare Custom Providers let us use the provider's **native HTTP schema**, including TypeSafe's `POST /v1/systemone`.

**Important:** the *gateway* is free. **TypeSafe Jev inference is not free merely because the request passes through it**. For `jev-1.14.0`, the upstream TypeSafe account/API key must still be available and may incur provider token charges. Cloudflare Unified Billing and purchased credits are not required and must remain disabled for the zero-cost policy. Cloudflare Workers AI separately has a daily free allocation, but its models are **not Jev**. Using them would require a separately benchmarked model adapter.

Official references:
- https://developers.cloudflare.com/ai-gateway/reference/pricing/
- https://developers.cloudflare.com/ai-gateway/reference/limits/
- https://developers.cloudflare.com/ai-gateway/configuration/custom-providers/
- https://developers.cloudflare.com/ai-gateway/features/unified-billing/
- https://developers.cloudflare.com/workers-ai/platform/pricing/

## Transport design

`JevSettings(route=JevRoute.CLOUDFLARE)` selects a fixed-host native path:

```text
https://gateway.ai.cloudflare.com/v1/{CF_ACCOUNT_ID}/{CF_GATEWAY_ID}/custom-typesafe/v1/systemone
```

Provision one free Cloudflare AI Gateway and a **custom provider** with slug `typesafe` and HTTPS base URL **`https://api.typesafe.ai`**. The actual path `/v1/systemone` is appended by Cloudflare. Do not include `/v1` twice. Restrict gateway authentication and use a scoped Cloudflare token. On gateway Settings, turn on **Require provider credentials**; transport also includes `cf-aig-no-wholesale: true` so requests must not fall back to Cloudflare Unified Billing. It sends the provider key in the upstream `Authorization` header and a separate Cloudflare gateway auth token in `cf-aig-authorization`. No endpoint hostname can be dynamically overridden. Config IDs/slugs are strictly validated.

Caching is bypassed for decision observations to avoid reusing a result out of context. Cloudflare logging must remain restricted to content-free metadata and bounded retention; disable sensitive request-body capture.

## Explicit activation gates

No environment configuration loader, production coordinator registration, automatic account creation or credential injection has been added. Construction of the Python Jev client needs all of:

- `mode=JevMode.SHADOW` (not authority)
- `route=JevRoute.CLOUDFLARE`
- `allow_metadata_egress=True`
- `allow_paid_requests=True` **only after a separately approved nonzero provider budget**
- a TypeSafe upstream secret plus Cloudflare account ID, gateway ID and Cloudflare gateway token

On the owner's **$0 requirement**, `allow_paid_requests=False` stays mandatory. This means **no actual Jev inference requests occur**. Do not add a fake TypeSafe key, buy credits, change Workers Free to Paid, or silently enable Unified Billing. Before *any* paid authorization, implement a hard atomic spend guard and conservative worst-case request reservation (including concurrency and retry), explicit owner approval and an auditable kill switch.

## Our own free gateway?

We could build a Cloudflare Worker reverse proxy or a lightweight Ruby/Python gateway, but that would only replace the **free** transport/control features already available in AI Gateway. It cannot make TypeSafe's proprietary compute free. A custom proxy adds another security and failure surface: credentials, replay, abuse control, tracing, and maintenance. Prefer the managed free gateway now.

For **actual $0 inference**, route existing Undermind Qwen/MiniLM observations to Node 001 when online or evaluate a Workers AI free-tier model only within its daily 10,000 Neurons allowance. Neither is Jev; both require their own measured quality gates. When free model quota or Node 001 is unavailable, keep deterministic policy as hard authority and skip optional classification rather than spending.

## Account configuration evidence (October 21, 2026)

The connected Cloudflare API verified the account containing the `ayahos` Pages project. It returned no pre-existing AI gateways or custom providers before provisioning. We created exactly one gateway `ayahos-undermind` and one **disabled** `typesafe` provider. Subsequent independent GET reads confirmed all security and $0-usage settings listed above. We did not use a TypeSafe key, configure an auto top-up, enable Workers AI paid routing, or send a provider request.

The gateway's `workers_ai_billing_mode` returned `postpaid` (Cloudflare default). **This field is not a $0 guarantee.** Under this project's policy, do not route Workers AI requests through this gateway until a hard eligibility/quota guard proves the free allowance and rejects all potentially chargeable calls. Existing inference routes were left unchanged.

Live application deployment identity is separately verified by `GET https://ayahos.pages.dev/api/build` returning `a8eeebdb4d18411747587b40f2deb01b9544abdd` (at the verification point). This is a build SHA check, not a completed inference test.

## Rollout evidence requirements

- Unit tests: off mode, provider credential absence, no network calls, Cloudflare exact URL, sanitized errors, model schema validation and no Unified Billing fallback header.
- Real Cloudflare gateway creation, upstream connectivity, TypeSafe billing/free credit, and Cloudflare Workers AI usage must be verified separately in the respective dashboards.
- No route may be enabled in live chat before full Octopus, security review, privacy approval, and spend-accounting gates pass.

## Idempotent free-tier provisioning (requires signed-in owner authorization)

An optional zero-dependency script, `scripts/provision_cloudflare_jev_gateway.py`, creates a **locked authenticated gateway** and **disabled** TypeSafe custom provider using Cloudflare's official API. It makes no inference calls and saves no API keys. It never enables Unified Billing or purchases credits.

In an owner-authorized terminal, set `CLOUDFLARE_ACCOUNT_ID` and a short-lived scoped `CLOUDFLARE_API_TOKEN` with **AI Gateway Read and Edit** (keep the token out of code, issue comments, CI logs, and chat). Then run:

```bash
python3 scripts/provision_cloudflare_jev_gateway.py
# dry-run: GET only, describes proposed changes
python3 scripts/provision_cloudflare_jev_gateway.py --apply
# creates the gateway with authenticated=true, byok_only=true, collect_logs=false,
# zero cache TTL and bounded rate limits; creates custom provider with enable=false
```

If an existing gateway lacks authentication or BYOK-only mode, or an existing `typesafe` provider has a mismatched base URL or is already enabled, **the script stops instead of overwriting it**. The script does not configure the provider credential; live Jev remains OFF. Account setup can alternatively be performed in the Cloudflare UI after signing in.

Never configure `JevSettings.allow_paid_requests=True` while the user requires $0 external inference.

## Strict $0 operating profile (2026-10-21)

**The proprietary TypeSafe Jev model is not a zero-cost model.** Cloudflare's model catalog advertises `typesafe/jev-1.14.0` as a third-party model at **$0.042 per 1 million input tokens**. A free AI Gateway does not waive inference charges: https://developers.cloudflare.com/ai/models/typesafe/jev-1.14.0/.

**Current permitted behavior:** Cloudflare gateway `ayahos-undermind` is enabled only as an authenticated free transport; custom provider `typesafe` is **disabled**. Application `JevSettings()` uses `mode=off` and `allow_paid_requests=False`; no Jev model queries, provider API key provisioning, retries or paid fallbacks. Setting `DUAL_LINEAGE_JEV_AUDIT_OFF_ENABLED=true` on an implementation that includes the new coordinator hook records the **off** state in Shared Spine without running or impersonating Jev.

**Existing model-only free option:** Use the project's already-implemented local Undermind shadow classifier (`DUAL_LINEAGE_SHADOW_ENABLED=true`; `DUAL_LINEAGE_SHADOW_BACKEND=bootstrap` for a lightweight, dependency-free heuristic, or `minilm` when a verified model artifact and sufficient memory are present). These are **not Jev**. `remote-minilm` on Node 001 should be used only after authenticating and verifying the reachable private node. Do not install heavyweight ML components on the free Render API service to force a model online. All routing and actions still rely on deterministic Undermind.

**Potential separately validated free model:** Cloudflare Workers AI advertises 10,000 free Neurons/day, hard-stopped on the **Workers Free plan**; certain models require Workers Paid even below that quota. Reference: https://developers.cloudflare.com/workers-ai/platform/pricing/. **Do not route Workers AI through this gateway yet:** its live `workers_ai_billing_mode=postpaid`, and the connected API could not verify this account's Workers billing plan. Its `byok_only` protection does *not* prevent Workers AI charging. Before activation, explicitly verify the actual Free plan, choose an eligible model, ensure fail-closed daily quota accounting, and benchmark risk/review score quality.

**Production costs are not proven zero solely by this gateway setting.** Other AyahOS provider routes, Render billing, and node electricity have independent cost policies. For the Jev/Cloudflare integration, no paid model inference is enabled or authorized under the current owner restriction.

### Repeatable read-only cost safety check

`scripts/verify_cloudflare_zero_spend.rb` fetches read-only Cloudflare API resources via Ruby, then passes a limited snapshot to the pure Python `scripts/verify_cloudflare_zero_spend.py` policy validator. Provide `CLOUDFLARE_ACCOUNT_ID` and a least-privilege `CLOUDFLARE_API_TOKEN` via protected environment variables, then run:

```bash
ruby scripts/verify_cloudflare_zero_spend.rb
```

The audit exits nonzero if gateway authentication/BYOK/no-logging/no-cache/ZDR/no-retry protection is weakened, the `typesafe` custom provider is enabled, automatic credit top-up becomes nonzero, or verification cannot be completed. It never sends an inference request and never creates, modifies, or purchases Cloudflare resources. A passing result **only** establishes the checked Jev gateway restrictions; it does not verify the billing tier for Workers AI, all AyahOS providers, or the user's total Cloudflare/Render invoice.
