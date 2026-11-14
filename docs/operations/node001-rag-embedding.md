# Node 001: free, local-only Qwen3 RAG embeddings

## What this is
This is a dedicated embedding **capability**, not a chat inference model and not an Undermind authority. It runs alongside the existing Node 001 cognitive worker without taking over its llama-swap port or GPU memory. The fixed model is `Qwen3-Embedding-0.6B-Q8_0.gguf` from `Qwen/Qwen3-Embedding-0.6B-GGUF`, size 639150592 bytes, pinned SHA256 `06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439`. It produces 1024-dimension vectors and binds only `127.0.0.1:8092` with `-ngl 0` (CPU-only). Model weights may be downloaded to `%USERPROFILE%\models` from their upstream source, and must be verified before use.

## Reproducible physical proof

On Node 001 (Windows PowerShell), use:

```powershell
.\deploy\node-001\run-qwen3-rag-embedding.ps1
.\deploy\node-001\run-qwen3-rag-embedding.ps1 -TestOnly
```

`-TestOnly` never starts or replaces processes. The launcher will fail closed on a checksum mismatch, unknown model, unexpected process occupying port 8092, missing embedding capability or dimensions, or an already-running server without CPU-only flags. It outputs structured proof without secrets. Python regression contract: `pytest -q tests/test_node_rag_embedding_launcher_contract.py`.

2026-10-23 physical Node 001 proof: official SHA256 matched; two nonzero 1024-element vectors completed in 70.1 ms CPU-only and private 127.0.0.1; existing chat port 8080 remained online. The server was kept local-only.

## Safety and production rollout boundary

**Do not** put `http://127.0.0.1:8092/v1/embeddings` in Render: on Render, localhost means Render itself, not Node 001. Do not open port 8092 to the public internet or set up an anonymous Cloudflare quick tunnel. Before wiring an `http` embedder, build and independently verify an HTTPS endpoint behind origin authentication, mTLS or a comparable documented private ingress and appropriate TLS hostname allowlisting. Inject any authentication keys solely via approved Render/compute secret management; do not print, commit, or transfer them through chat.

For a future verified endpoint: `DUAL_LINEAGE_RAG_EMBEDDING_BACKEND=http`, `DUAL_LINEAGE_RAG_EMBEDDING_MODEL=Qwen3-Embedding-0.6B-Q8_0`, `DUAL_LINEAGE_RAG_EMBEDDING_DIMENSIONS=1024`, and HTTPS `DUAL_LINEAGE_RAG_EMBEDDING_URL=https://<protected-host>/v1/embeddings`. The existing request-level cloud and control envelope checks still apply. Match vector dimensionality to the existing RAG HNSW column, verify first under a test-only/limited request, then do reversible batch re-embedding of curated corpus with explicit operator approval, and ensure a full grounded citation trace.

This local proof **does not** establish a reachable production vector inference endpoint or deployed vector retrieval. The production RAG may remain lexical until security, policy and end-to-end validation are complete. Chat provider/model settings must remain independent.
