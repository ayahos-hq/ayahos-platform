# Aliyun production recovery (October 2026)

This is a no-spend recovery procedure for the AyahOS Render API. Model Studio
chat quotas and embedding billing are separate. Do not treat a key being present,
a successful `/models` response, or a provider health 200 as proof of free tokens.

## Current safeguards

- `render.yaml` defaults `DUAL_LINEAGE_RAG_EMBEDDING_BACKEND=none`; lexical
  retrieval and citations remain available. DashScope `text-embedding-v4` does
  **not** share the chat free quota. Enabling it requires separate spending
  authorization, verified pricing and a controlled live probe.
- Aliyun chat requires an existing Singapore-region pay-as-you-go
  `DASHSCOPE_API_KEY`, matching `DASHSCOPE_ENDPOINT`, a role model, and *both*
  nonnegative USD-per-million token prices. The provider is still removed if
  `DUAL_LINEAGE_DISABLED_PROVIDERS` contains `aliyun` or `aliyun-overmind`.
- If a key is present but a model or pricing is missing, registration logs now
  state `aliyun-overmind not registered: missing_model` or `missing_pricing`,
  without revealing the key. A disabled route still logs the operator removal.
- Logging and cost estimates are **not billing controls**. No application-only
  token counter can prevent fees at the model provider.

## Activate without surprise billing

1. In the Alibaba Model Studio Singapore console, verify free quota remaining
   **and expiration for the exact model**. Enable **Free Quota Only** for *each*
   model intended for routing before any chat call. The switch is off by default.
   The Alibaba docs say calls otherwise become pay-as-you-go automatically.
   Verify the switch is effective, not merely requested; if quotas are exhausted
   and the console cannot enable the mode, keep that model disabled.
2. Inspect Render **configuration**, not key values. Preserve unrelated
   disabled providers, secrets and environment variables. Use the Singapore
   endpoint `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` only for a
   matching Singapore credential. Select *one verified free-only* Qwen model,
   set `DUAL_LINEAGE_ALIYUN_OVERMIND_MODEL`, and set the matching published
   `DUAL_LINEAGE_ALIYUN_OVERMIND_INPUT_USD_PER_M` and
   `DUAL_LINEAGE_ALIYUN_OVERMIND_OUTPUT_USD_PER_M`. Pricing is for runtime
   accounting, **not** permission to spend.
3. Remove only the Aliyun ID from `DUAL_LINEAGE_DISABLED_PROVIDERS` if present.
   Keep all unrelated provider disabled entries. Deploy, then inspect the
   private `/v1/runtime/health` or operator runtime panel to confirm the route
   is registered. A 200 alone does not prove completion.
4. With Free Quota Only independently verified, run a single authorized low
   token real-time chat request. Require visible output, exact model ID,
   provider ID, usage, request trace and success. Do not perform automated
   paid-model or embedding probes.
5. For failover, repeat the console quota and switch verification for every
   target model. Runtime fallback does not imply that another model is free.
   Do not silently rotate model IDs or increase the fallback count.

## Roll back

Add `aliyun` to `DUAL_LINEAGE_DISABLED_PROVIDERS`, *without removing other IDs*,
and keep `DUAL_LINEAGE_RAG_EMBEDDING_BACKEND=none`. This intentionally returns
chat to other allowed providers (if any) and keeps RAG lexical. Re-check public
chat and keyless `/health`. Do not wipe the entire environment or touch secrets.

References: [Alibaba Model Studio free-quota rules](https://www.alibabacloud.com/help/en/model-studio/new-free-quota)
and [standard model pricing](https://www.alibabacloud.com/help/en/model-studio/model-pricing).
