# Provider onboarding and brain routing

AyahOS Dual-Lineage treats a provider credential and a brain model profile as different things.
A vendor key can therefore back an expensive Overmind model and a fast Undermind model without
forcing both lineages onto the same model.

## Roles

- **Overmind / cognitive**: planning, reasoning, coding, synthesis, long-context work.
- **Undermind / autonomic**: short structured critique, risk/uncertainty review, fast second-pass checks.
- **Embedding**: remains isolated in the existing local MiniLM path. Chat providers are not silently
  reused as embedding providers.

The deterministic Undermind policy remains authoritative. The autonomic model is advisory-only.

## Provider families

Implemented adapters and profiles:

| Vendor | Transport | Assigned lineage |
| --- | --- | --- |
| llama.cpp | OpenAI-compatible local | local Overmind + local Undermind |
| Ollama | OpenAI-compatible local | local Overmind + local Undermind |
| OpenAI | OpenAI-compatible | Overmind: reasoning, coding, tools |
| Azure OpenAI | OpenAI-compatible | Overmind: enterprise reasoning and coding |
| Anthropic | native Messages API | Overmind: reasoning, coding, long context |
| Vertex AI | OpenAI-compatible + renewable ADC auth | Overmind: multimodal and long context |
| Gemini Developer API | OpenAI-compatible | Overmind: multimodal and low latency |
| DeepSeek | OpenAI-compatible | Overmind: coding, agents, cost efficiency |
| Groq | OpenAI-compatible | Undermind: low latency and structured critique |
| SiliconFlow | OpenAI-compatible | Undermind: open models and cost efficiency |
| Alibaba Model Studio | OpenAI-compatible | Overmind: Qwen reasoning and coding |
| Amazon Bedrock | OpenAI-compatible | Overmind: enterprise model breadth |
| Together AI | OpenAI-compatible | Undermind: open-model fallback |
| Cohere | OpenAI-compatible | Undermind: retrieval and structured critique |
| Hugging Face | OpenAI-compatible | Undermind: open-model fallback |

These assignments are deliberate routing boundaries, not claims that one company is universally
better. The actual model ID is explicit for the assigned lineage. A provider is never instantiated
for the other lineage by the factory, even if an operator supplies that lineage's environment
variables.

## Environment convention

For a vendor slug such as `OPENAI`, `GROQ`, `VERTEX`, or `DEEPSEEK`:

```text
DUAL_LINEAGE_<VENDOR>_OVERMIND_MODEL=
DUAL_LINEAGE_<VENDOR>_OVERMIND_INPUT_USD_PER_M=
DUAL_LINEAGE_<VENDOR>_OVERMIND_OUTPUT_USD_PER_M=
DUAL_LINEAGE_<VENDOR>_OVERMIND_CONTEXT=8192
DUAL_LINEAGE_<VENDOR>_OVERMIND_PRIORITY=

DUAL_LINEAGE_<VENDOR>_UNDERMIND_MODEL=
DUAL_LINEAGE_<VENDOR>_UNDERMIND_INPUT_USD_PER_M=
DUAL_LINEAGE_<VENDOR>_UNDERMIND_OUTPUT_USD_PER_M=
DUAL_LINEAGE_<VENDOR>_UNDERMIND_CONTEXT=8192
DUAL_LINEAGE_<VENDOR>_UNDERMIND_PRIORITY=
```

A cloud role profile is not registered unless its API credential, model ID, and both token prices
are present. That prevents an unknown model from being treated as zero-cost.

## Vertex AI

Vertex is separate from the Gemini Developer API. It uses:

```text
VERTEX_AI_PROJECT=
VERTEX_AI_LOCATION=us-central1
```

Authentication is obtained through Google Application Default Credentials and refreshed for calls.
The role model IDs still use the standard `DUAL_LINEAGE_VERTEX_*_MODEL` convention.

## Gemini Developer API (AyahOS project)

This is the first Google integration to configure for AyahOS. It uses the existing
OpenAI-compatible Overmind route, not Vertex or a second inference stack. A key must
belong to the intended **AyahOS** project; the other projects visible under the same
Google login are separate quota and billing boundaries. Keep the key in a masked
runtime secret store, never in this repository or a queued ingestion job.

```text
GOOGLE_AI_API_KEY=<masked secret for the AyahOS project>
DUAL_LINEAGE_GEMINI_OVERMIND_MODEL=<model enabled for that project>
DUAL_LINEAGE_GEMINI_OVERMIND_INPUT_USD_PER_M=<published input rate>
DUAL_LINEAGE_GEMINI_OVERMIND_OUTPUT_USD_PER_M=<published output rate>
```

Set both rates to the applicable published rates for the account and model; do
not assume that student status or a free-tier label makes production usage free.
The route stays absent if any required setting is missing. It is cognitive-only,
and a request must independently permit cloud execution. A local mock test checks
the endpoint, bearer header, role boundary, and cost arithmetic; it does **not**
prove that the account can create a key or make a live request. Verify project,
quota, billing, and a small authenticated request before enabling live routing.

Next in utility is read-only Google Drive ingestion, but private Drive files
require an explicit OAuth consent scope and a token lifecycle. The existing
Ruby ingestion URL connector can already ingest explicitly public text URLs;
do not use it as a substitute for authorized private Drive access. Cloud Run
and Vertex remain separate, billing-dependent deployment/inference paths.

## Amazon Bedrock

Bedrock uses its OpenAI-compatible runtime endpoint. Configure `AWS_REGION` and
`AWS_BEDROCK_API_KEY`, or set `AWS_BEDROCK_BASE_URL` explicitly. Bedrock runtime does not expose
the compatible `GET /models` endpoint, so its cheap health probe is intentionally marked
unsupported rather than faking a healthy result.

## Routing behavior

1. Deterministic Undermind preflight runs first.
2. Heavy cognitive requests with no explicit provider enter the horizontal compute pool.
3. Eligibility is filtered by local/cloud permission, live node capacity, model compatibility, and
   configured cloud-provider profiles.
4. Rendezvous hashing on the request ID ranks the eligible peers and elects the first. There is no
   fixed first peer. If the elected peer is unavailable, the request moves down that per-request
   ranking within the rollout fallback budget (see [`routing-rollout.md`](routing-rollout.md)).
5. An explicit vendor request such as `openai` remains an explicit override and fails closed when
   unavailable or forbidden.
6. Standard non-heavy requests retain the normal role-aware provider path.
7. The autonomic critic chooses only AUTONOMIC routes and remains advisory-only.

## Verification levels

Unit tests prove adapter normalization, role separation, model allowlisting, cost calculation,
Vertex bearer auth injection, and routing policy. They do not prove that external credentials are
valid or that any provider is currently healthy. Live verification remains a separate evidence step.


## Horizontal compute fabric

AyahOS keeps heavyweight model execution off Render. Render is the control plane for API/auth,
routing, registry, policy, telemetry, and evidence coordination.

Node 1, Oracle, AWS Bedrock, and Aliyun are current compute-plane examples, not tiers or a closed
allowlist. Every live cognitive node in the Compute Registry and every configured cognitive provider
route that passes permission checks joins the same candidate set dynamically. The runtime uses
rendezvous hashing on the request ID to rank the peers and elect the first. A request does not
walk a fixed Node 1 → Oracle → AWS → Aliyun chain; its bounded fallback follows its own ranking.

If the elected peer is unavailable when the request reaches it, the request moves to the next ranked
peer, within the rollout fallback budget and the request's one runtime deadline (see
[`routing-rollout.md`](routing-rollout.md)). Only a peer failure moves it on: a cancellation, an
exhausted deadline, a policy denial, or a request fault is terminal, and a pinned provider never
fails over. Subsequent requests are re-elected from the then-current eligible fabric. No static
membership/order variable is required.

`workload_class` may be `auto`, `standard`, or `heavy`. Auto classification uses only
control-plane signals: requested token budget and prompt byte size. Shadow complexity is telemetry
only and cannot select the heavy plane. The cognitive model cannot self-promote into a heavier
compute class.

Oracle is eligible only after its node agent registers through the standard heartbeat protocol.
Node 1 remains cognitive-only by contract. The separate MiniLM learning worker is also compute-plane
work and is not hosted on Render.

Heavy SSE requests use the same election. Provider peers stream natively; node peers return a
buffered result that is emitted through the SSE surface without pretending the node itself streamed.

## Routing rollout

How routing decisions and cross-provider failover are enabled in stages (observe mode, fallback percentage,
provider comparison, retirement) is in [`routing-rollout.md`](routing-rollout.md).
