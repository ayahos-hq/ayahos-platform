# Jev through OpenCode Zen: free promo route (shadow only)

## What this route is

OpenCode Zen lists **Jev 1.13 Free** (`jev-1.13-free`) as a limited-time free
model on its TypeSafe-compatible endpoint:

```text
POST https://opencode.ai/zen/v1/systemone
```

The response is the native Jev wire shape (`model`, `answers` with `noul`
probabilities, `usage`), so the existing Jev client parses it through the
same path as the direct TypeSafe route. `JevSettings(route=JevRoute.ZEN,
model="jev-1.13-free")` selects it; the runtime builder
(`_build_jev_observer`) prefers this route whenever
`DUAL_LINEAGE_JEV_ZEN_ENABLED` is set, ahead of the Vercel credit route and
the audit-off observer.

## Limits and non-claims

- **Limited-time promo, not a contract.** The free model can end, change, or
  start rate-limiting at any time. Nothing in AyahOS may depend on it
  continuing to exist.
- **It is Jev 1.13, not the pinned Jev 1.14.** The Vercel/direct routes pin
  `jev-1.14.0`; this route serves `jev-1.13-free`. Scores from the two
  versions are not interchangeable calibration data.
- **Shadow / advisory only, as always.** A Zen observation is recorded as
  Shared Spine evidence after deterministic preflight. It cannot change a
  `ControlEnvelope`, authorize an action, or mint a lease. Deterministic
  Undermind policy remains authoritative, and a failed or unavailable Zen
  call never blocks chat.

## Cost and credentials

The route is $0 and **keyless works**: no account and no API key are
required. An optional free OpenCode Zen key may raise rate limits; set it as
`DUAL_LINEAGE_JEV_ZEN_API_KEY` (Render secret, `sync: false`) and the client
sends it as the `Authorization` header. The Zen gate in `JevSettings` refuses
activation when `allow_paid_requests` is true, so this route cannot quietly
become a paid route.

## Operational gotchas

- **User agent:** the Zen gateway WAF rejects bare/python default user
  agents. The client sends `User-Agent: curl/8.9.1` on this route only.
- **Model name:** free access requires exactly `jev-1.13-free`; aliases
  such as `jev-latest` return 401 on free access.
- **Transient 500s:** the gateway occasionally returns a fast (~1s) 500.
  The Jev client deliberately has **no retries**; the observer records the
  observation as `unavailable` and the request proceeds under deterministic
  policy alone. A rising `unavailable` rate is the expected symptom when the
  promo ends or rate limits bite.

## Egress contract

Identical to the other Jev routes: only the content-free `JevSafeState`
metadata (stage, action kind, coarse permission/risk flags, tool count)
leaves the API, and only when metadata egress is enabled by the route's
settings. No prompt text, request metadata, RAG content, tool names, or
request IDs are transmitted.

## Activation and kill switch

`render.yaml` configures the API service with
`DUAL_LINEAGE_JEV_ZEN_ENABLED="true"` and `DUAL_LINEAGE_JEV_ZEN_API_KEY`
declared `sync: false` (unset = keyless). **Kill switch:** set
`DUAL_LINEAGE_JEV_ZEN_ENABLED=false` (or remove it) and redeploy; the
runtime falls back to the Vercel gate, then the audit-off observer, then no
observer.

## Verification

- Mock-transport tests: `apps/api/tests/test_jev_zen_route.py` (settings
  gates, endpoint, keyless/keyed headers, recorded-response parsing, 500
  fails closed with no retry, runtime builder precedence).
- Sandbox live probe, 2026-10-22: the new client code, keyless, against
  the real endpoint returned a valid observation for a preflight state —
  model `jev-1.13-free`, high-impact 0.03, needs-review 0.72, usage
  366 input / 39 output tokens. That is **verified-live for the endpoint
  probe itself**. Render activation is **configured**, not verified-live,
  until the deploy of this change lands and a live chat request records an
  `observed` Jev event.
