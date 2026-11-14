# Jev 1.14 through Vercel AI Gateway: credit-only activation

Source of truth (verified October 22, 2026):
- https://vercel.com/docs/ai-gateway/pricing
- https://vercel.com/docs/ai-gateway/sdks-and-apis/rest-api
- https://vercel.com/changelog/ai-gateway-now-supports-typesafe-clients-and-http-api-for-jev
- https://vercel.com/ai-gateway/models/jev-1.14.0

## Scope and financial boundary

Cloudflare Pages remains AyahOS's public frontend. Vercel's existing site deployment is still a **frozen rollback**. The new route uses only **Vercel AI Gateway as an outbound evaluation transport**, not Vercel hosting.

Vercel advertises **$5 free Gateway credits every 30 days** for teams that **have not purchased credits**. The free credits may be used across its catalog, including the listed `typesafe-ai/jev-1.14.0` model at approximately $0.04 per million input tokens. **This credit is conditional, not a free model.** Credit purchase moves an account to a paid tier that no longer receives monthly free credit.

**Do not activate inference unless all of the following have been verified on the exact Vercel team:**

1. The account is on the AI Gateway **free-credit** tier, and has **never purchased** gateway credits.
2. Current available **free** balance is positive with at least $0.10 left as a safety reserve. The free balance begins with the account's first eligible Gateway request; an empty account cannot be assumed funded.
3. Auto top-up is **OFF**, and no connected provider BYOK route/system credential fallback could charge a provider account.
4. A new dedicated **AI Gateway** key (not a generic Vercel API token) is created for AyahOS Jev with **$4.50 non-renewing spend quota**, no BYOK, and least privilege. Vercel's key budgets are *soft caps*, so the hard barrier is prepaid credits plus disabled auto top-up.
5. The model `typesafe-ai/jev-1.14.0` is **eligible** for this team. Verify via the Gateway catalog or authenticated `GET /v1/models?include_availability` (request context must be available).
6. Obtain an independently verified actual model response and per-request receipt without sending user text. Do this in a controlled environment first.

The connected Vercel management tool can read the project but **did not permit reading the team's AI Gateway balance, accessing project env variables, or creating budgeted AI Gateway API keys**. The rollout is therefore incomplete until the owner completes the secure Gateway login and key creation. No account funds are assumed and no paid inference should run automatically.

## Operator commands

In Vercel's dashboard, open the correct team > **AI Gateway**. Check the credit balance and tier, disable auto top-up, review BYOK/system fallback, and create a **dedicated budgeted** Gateway API key. Store the key in the **Render API service's encrypted environment**, never GitHub or a public site variable. The Vercel site deployment remains unchanged.

After the above have been independently verified, update the existing free Render API service only:

```text
AI_GATEWAY_API_KEY=<secret stored only in encrypted Render environment>
DUAL_LINEAGE_JEV_VERCEL_ENABLED=true
DUAL_LINEAGE_JEV_VERCEL_FREE_CREDITS_VERIFIED=true
DUAL_LINEAGE_JEV_AUDIT_OFF_ENABLED=true
DUAL_LINEAGE_SHADOW_ENABLED=true
DUAL_LINEAGE_SHADOW_BACKEND=bootstrap
```

The runtime requires all three conditions: explicit enabled flag, verified-free-credit attestation, and gateway key. Otherwise Jev stays OFF and the local bootstrap observer continues.

The client uses Vercel's **official** `POST https://ai-gateway.vercel.sh/v1/evaluate` for `typesafe-ai/jev-1.14.0`, with two fixed `boolean` questions and content-free structured metadata in `state`. The response's two `probability` fields are recorded as **non-authoritative** advisory Shared Spine evidence. Neither model output can change an Undermind envelope, authorize tools, or execute actions.

Before every inference, the client reads authenticated `GET https://ai-gateway.vercel.sh/v1/credits` and **refuses the provider request** if it cannot verify a balance of at least $0.10. It uses bounded requests and responses, a fixed endpoint, no retries/redirects, and no environment proxies. No implicit fallback to direct TypeSafe or Cloudflare's disabled custom provider.

**Important:** A positive credit balance is not evidence that credits were free. The operator account check remains mandatory. The reserve check is also not an atomic distributed budget or proof of zero charges if account-level settings change. Use the gateway's prepaid balance, account-level auto-topup OFF, and a dedicated key's spend quota as independent controls.

## Verification before rollout

```bash
pytest -q apps/api/tests/test_jev_vercel_credit_route.py apps/api/tests/test_jev_vercel_runtime.py
ruff check apps/api/src/dual_lineage/brains/undermind/jev/ apps/api/src/dual_lineage/runtime.py
make mypy
make api-test
```

Run required Octopus acceptance for the exact merged commit and verify live chat in both buffered and SSE paths with **no user text in the Jev request**. Compare Shared Spine event `status=observed` and the Gateway usage receipt with the budget, model ID and deployment commit. Test 401/429, depleted credits, malformed model response, and disabled flags.

## Emergency rollback

1. Immediately set `DUAL_LINEAGE_JEV_VERCEL_ENABLED=false` on Render. The Jev adapter then sends **zero** Vercel requests.
2. Keep `DUAL_LINEAGE_JEV_AUDIT_OFF_ENABLED=true` if you want content-free OFF status records.
3. Revoke the dedicated Jev Gateway key if there is suspected credential exposure.
4. Confirm the existing local bootstrap classifier and deterministic Action Gateway remain operational.

**No account purchase, top-up, plan change, or chargeable probe is authorized by this document.**
