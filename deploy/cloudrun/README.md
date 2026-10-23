# Cloud Run staging — zero-spend gate

**State:** repository preparation only. Not built or tested in Google Cloud, deployed, or serving traffic. Render remains the live backend. No secrets, provider tokens, billing operations or Cloudflare routing changes are authorized by this configuration.

`staging-target.json` is the reviewed **desired state**, not a Cloud Run API
manifest or proof of deployment. The generic `hello-service` design using
`us-docker.pkg.dev/cloudrun/container/hello`, external ingress, and up to 10
instances is Google's sample architecture, not the AyahOS staging target. Do
not deploy it or point AyahOS traffic at it. An eventual staging deployment must
use the target's explicit project and region, an AyahOS image pinned by
`@sha256:`, internal ingress, authenticated invocation, at most one instance,
and no traffic. The image and service identity are intentionally not supplied
by this repository; neither a placeholder nor a tag is a deployable image.

## Decision

Cloud Run is an optional *CPU-only* control-plane host, not the model host. The dedicated image `Dockerfile.cloudrun` includes Python FastAPI, deterministic Undermind, Overmind dispatch, Action Gateway and Shared Spine code. Model weights, Torch, ONNX, transformers, local inference, local ML training, document stores, Ruby RAG, Ruby worker and operator web are not bundled. Aliyun/DashScope, Oracle, Node 001 and AWS Bedrock stay separately controlled inference targets.

**Hard cost requirement:** the user requires actual spend of $0. Cloud Run's advertised monthly free tier does **not** itself guarantee $0: it requires an active billing account and excess usage, outbound network traffic, Cloud Build, Artifact Registry and other products can be billed. Neither billing alerts nor `--max-instances` provide an absolute all-service cost guarantee. For this reason, **do not deploy, enable paid APIs, create a registry, reinstate billing, or switch production traffic before verifying the account and an enforceable zero-spend solution across all affected products.** Cloud Run spend-cap budgets cover Cloud Run but do not cap all Google Cloud products and are not instant. If a hard $0 guarantee cannot be established, keep the service unprovisioned and choose an existing no-charge resource instead.

## Separation of concerns

- Public site: Cloudflare Pages/Functions, with browser-safe configuration only.
- Cognition API: this private Cloud Run *candidate*, one Python worker, bounded request time and resources, no local ML. No inference credentials in the image.
- Persistent Spine / evidence: existing Supabase PostgreSQL, but **not enabled in the first smoke stage**. Local mode is ephemeral and must never be promoted as durable.
- Inference: Node 001, Oracle, Aliyun/Qwen, Bedrock and other separately authorized providers; model inference must not be scheduled on Cloud Run.
- Optional RAG: absent from slim stage; cannot claim feature parity until the existing Ruby RAG is replaced or securely exposed elsewhere and retested.
- Operator/admin UI, MCP bridges and webhooks: remain on existing destinations until independently migrated and proved.
- Octopus: authoritative CI, including a green release gate. No Cloud Run auto-deploy workflow is included.

## Current blockers

1. Read-only CLI verification on October 21, 2026 found the active credential
   `ayahos.dev@gmail.com`, the `AyahOS` project
   `project-eec9b975-b6bd-4b41-bad`, `billingEnabled=false`, and the Cloud Run
   Admin API disabled. Describing `hello-service` in `us-central1` returned
   `SERVICE_DISABLED`; this does not prove whether a design exists elsewhere.
2. No inspected evidence shows Cloud Run, Cloud Build, Artifact Registry, and networking together can operate with a hard $0 payment guarantee on this account.
3. No approved immutable AyahOS image digest, staging credentials, durable
   staging database, or functional hosted acceptance evidence exists.

## Free-safe work now

1. Review slim image files and run local build/tests on an authorized workstation (no cloud billing required).
2. Check static gates: image contains only `apps/api[control]`, API binds to `$PORT`, `--workers 1`, no Ruby/model assets, nonsecret staging env disables writes/network side effects and remote paid provider calls by default.
3. Compare cold-start footprint, memory and CPU with the free limits using a local 512 MiB test container; a passing `/health` alone is not sufficient.
4. Keep the branch as a non-deploying PR. Merge code only after the gates and repository conflicts are resolved; merging **must never create a paid cloud resource**.
5. Before any hosted smoke, choose an AyahOS-specific project, verify account eligibility and billing status, identify the exact Cloud Run limits/costs and external-service usage, and confirm a genuine zero-cost boundary. If any step may charge, **stop** and retain Render.

## If an eligible fully controlled no-charge account becomes available

For an explicitly approved private, CPU-only *staging* trial:

- Region: select an eligible region using current pricing, latency and available quota evidence.
- Minimum instances: 0; maximum instances: 1; request-based CPU; 1 vCPU; 512 MiB; concurrency: 2; one Python worker; no GPUs.
- IAM-only invocation (`--no-allow-unauthenticated`), dedicated least-privilege runtime principal; don't paste or commit secrets.
- Use a tested immutable image digest and verified release SHA.
- Nonsecret defaults: `deploy/cloudrun/staging-env.yaml`; no Cloud provider keys, no Cloud Run paid inference, RAG off, shadow off, agent off and write/exec/network/action side effects denied.
- First prove `/health`, then verify fail-closed `/v1/cognition` when runtime authentication is deliberately unconfigured.
- Provision separate staging secrets through an approved secure secret store before testing authenticated chat. Do not reuse production keys.
- Run schema migrations **once** through controlled release operations, then switch to an isolated durable staging DB. Never migrate the production DB at application cold-start.
- Exercise role-aware Aliyun/Oracle/Node 001/AWS routing with per-provider spend controls and a strict $0 allowance (not automatically implied by Cloud Run's allowance).

`deploy/cloudrun/cloudbuild.yaml` is a *manual-only* potential build recipe. Executing it can generate Cloud Build, Artifact Registry or network charges. **Do not execute it under the current strict $0 policy.**

## Functional promotion gates

- An Octopus green run at the exact deployed commit.
- Public and private authentication fails closed when no proper secret is configured.
- Undermind deterministic enforcement and Action Gateway permissions remain unchanged.
- Long SSE streams, partial output, cancellation, idempotence, rate limiting, resource caps and provider failure paths pass.
- Supabase-backed Shared Spine traces persist correctly across restarts.
- Ruby RAG and webhook capabilities are either preserved and tested or are explicit non-migration blockers.
- Cost measurement proves no chargeable dependency, not merely that a free quota appears sufficient.
- Cloudflare and Vercel backup routing verified on staging; production remains on Render until proven.
- Reversible canary and rollback tested without replaying non-idempotent actions.

## Provider portability

Any future migration should change only infrastructure adapters and environment bindings. Keep the **Overmind / Undermind / Shared Spine** authority model, fail-closed auth and separate provider pool independent of Cloud Run. No infrastructure host can gain action authority just by running the API.

## Trusted references

- https://cloud.google.com/run/pricing
- https://docs.cloud.google.com/free/docs/free-cloud-features
- https://docs.cloud.google.com/billing/docs/how-to/budgets
- https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps
