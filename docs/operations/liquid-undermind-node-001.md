# Liquid LFM as the Undermind critic, on Node 1

Status vocabulary (per AGENTS.md): the integration below is **configured** —
no code change was needed, and nothing here is **verified-live** until the
desktop run in the last section has been done and recorded. The model
wiring was exercised locally against the real GGUF during development;
that is **verified-local** for the provider/critic path only, not a
physical Node 1 GPU proof (that gate remains
`docs/operations/physical-node-001-proof.md`).

## What this is

Liquid AI's LFM2.5-1.2B-Instruct (official GGUF, Q4_K_M, 730,895,168 bytes,
sha256 `b1b3de114215d9507409a662a501a631095a479a419584e8a2ded6304b19b4f5`,
LFM Open License v1.0 — free commercial use under $10M revenue) replaces
Qwen3-0.6B as the model behind AyahOS's autonomic critic
(`brains/undermind/critic.py`, `AutonomicCritic`).

Why it fits, and where it does not:

- The critic's whole job is one short, strict-JSON assessment (max 256
  tokens, temperature 0) when the shadow classifier crosses the 0.65
  threshold. A small, fast, instruction-tuned model built for CPU/edge
  inference is the right shape for that; the LFM is that, and it is a
  stronger instruction follower than a 0.6B model at roughly the same
  footprint.
- It stays **advisory-only**. Critic output cannot alter a
  `ControlEnvelope`, authorize, or veto anything; deterministic Undermind
  policy remains authoritative (invariants 1–3). Swapping the critic
  model changes no authority boundary.
- It is **not** a classifier replacement. The MiniLM shadow classifier
  is a separate stack with its own change process; the LFM
  encoder/embedding variants are deliberately excluded here.
- It is **not** an Overmind/cognitive model. It never registers as a
  cognitive route.

## Where it runs: Node 1, the local desktop

Node 1 (`node-001`, "Mind 1") is the operator's local desktop
(RTX 3060 12 GB, Windows). It is pinned **cognitive-only** in
`apps/api/src/dual_lineage/compute/config.py` (`fixed_role_for`), and the
Compute Registry strips any other role from its heartbeats. So the LFM
cannot be advertised by `node-001`, even though it sits on the same
physical machine. Two supported wirings, both honouring that contract:

### A. Direct local provider route (simplest; local dev / co-located API)

`providers/factory.py` already builds an `undermind-local`
`LlamaCppProvider` (role `autonomic`, priority 120) whenever
`DUAL_LINEAGE_UNDERMIND_URL` is set, and `runtime._build_critic` adopts
that provider's default model. Configuration only:

```text
DUAL_LINEAGE_UNDERMIND_URL=http://127.0.0.1:8082
DUAL_LINEAGE_CRITIC_ENABLED=true
DUAL_LINEAGE_CRITIC_MODEL=lfm2.5-1.2b
DUAL_LINEAGE_CRITIC_THRESHOLD=0.65
DUAL_LINEAGE_CRITIC_MAX_TOKENS=256
DUAL_LINEAGE_CRITIC_TIMEOUT_MS=5000
DUAL_LINEAGE_UNDERMIND_CONTEXT=8192
DUAL_LINEAGE_UNDERMIND_QUANT=Q4_K_M
DUAL_LINEAGE_UNDERMIND_API_KEY=   # only if the llama-server requires one
```

Notes:

- `DUAL_LINEAGE_UNDERMIND_URL` is the llama-server base URL **without**
  `/v1`; the provider appends `/v1/chat/completions`.
- `DUAL_LINEAGE_CRITIC_TIMEOUT_MS` is raised from the 2000 ms default:
  256 output tokens plus first-token latency is tight at 2000 ms even on
  the 3060. Critic timeouts fail safe (recorded unavailable; the request
  itself is unaffected), but a critic that always times out is noise.
- If the API is the hosted Render service rather than a co-located one,
  loopback will not reach the desktop. Point the URL at the desktop's
  existing private tunnel endpoint (HTTPS) instead; never expose the
  llama-server port publicly without its API key set.

### B. Compute-fabric route (registered node; live fleet)

Run a **second** node-agent instance on the desktop as `undermind-001`
(pinned autonomic-only), beside the existing `node-001` agent:

- env template: `deploy/node-001/undermind-001.env.example`
  (`DUAL_LINEAGE_NODE_ID=undermind-001`, agent port 8111, backend the
  LFM's llama-server on 8082, `DUAL_LINEAGE_NODE_AUTONOMIC_MODEL=lfm2.5-1.2b`)
- and set `DUAL_LINEAGE_CRITIC_USE_COMPUTE=true` on the API so the critic
  dispatches through the Compute Registry instead of a provider route.

## Serving the model on the desktop

Preferred: a dedicated, always-warm llama-server —
`deploy/node-001/start-undermind.ps1` (verifies the GGUF's SHA256 before
launch, `--alias lfm2.5-1.2b`, full GPU offload, ctx 8192, loopback
:8082). The alias must match `DUAL_LINEAGE_CRITIC_MODEL` /
`DUAL_LINEAGE_NODE_AUTONOMIC_MODEL` exactly, because the provider sends
that string as the request's model.

Alternative: add `deploy/node-001/llama-swap-undermind.yaml` to the
existing llama-swap config. Accepted, with the eviction/cold-load
trade-off documented in that file.

Deliberately excluded: LFM2.5-24B-A2B (does not fit the fleet's 12 GB
nodes as a resident utility model, and is far more than a 256-token
critic needs) and all LFM encoder/embedding variants (classifier stack,
separate process).

## Verification (desktop run, to be recorded)

One-command path: `deploy/node-001/run-liquid-undermind.ps1` downloads
and SHA256-verifies the GGUF, finds or downloads llama.cpp (Vulkan
b10964), serves the model, runs the critic probe below twice (cold and
warm), and writes a `liquid-undermind-node001-run/v1` evidence JSON.
Steps 1–2 are its manual equivalent.

1. `start-undermind.ps1` runs; `GET http://127.0.0.1:8082/v1/models`
   lists `lfm2.5-1.2b`.
2. One direct `POST /v1/chat/completions` with the critic prompt shape
   returns exactly one JSON object matching the critic schema
   (`recommendation`, `risk_score`, `uncertainty_score`, `confidence`,
   `reason_codes`) — the critic's parser accepts strict JSON or a
   fenced block; anything else is a parse failure, recorded as critic
   unavailable.
3. With wiring A or B in place, force a shadow prediction at/above the
   0.65 threshold and confirm the request trace records a
   `CriticAssessment` with `model=lfm2.5-1.2b` and a policy/critic
   comparison whose authority is `deterministic_undermind`.
4. Record date, deployed API commit SHA, wiring used, and observed
   critic latency here / in `docs/PROJECT_STATE.md` before claiming
   **verified-live**.
