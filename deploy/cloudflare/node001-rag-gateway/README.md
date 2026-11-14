# Node 001 free embedding gateway

This worker exposes **only** `POST /v1/embeddings` and an authenticated `GET /health`. It uses the fixed-target Cloudflare Workers VPC Service bound as `PRIVATE_EMBEDDER`. The private origin is `127.0.0.1:8092` on Node 001 and must never have a public inbound firewall rule. The worker has no chat inference capability and does not replace Overmind or Undermind.

## Runtime

- Tunnel: `ayahos-node001-embedding` (`325f85b9-8162-4de8-aed2-d1fa73ef922c`)
- VPC service: `ayahos-node001-rag-embeddings` (`01a167d6-2244-7191-9c3b-62b229f6bd1a`)
- Origin: Qwen3-Embedding-0.6B Q8_0, 1024-dimensional, CPU only, loopback 8092.
- Worker: `ayahos-node001-rag-gateway`.
- Transport: authenticated HTTPS Worker -> scoped Workers VPC Service -> outbound QUIC tunnel -> Node 001 HTTP loopback.

## Security and cost

The public route must remain **disabled** until `API_TOKEN` is securely set as a Worker secret and the **same secret** is stored as `DUAL_LINEAGE_RAG_EMBEDDING_API_KEY` in Render, using approved secret-management tools. Never check the value into Git, display it in a log or share it in chat. The code fails with HTTP 503 if the credential or VPC binding is absent; it returns HTTP 401 without a valid bearer token. Only the pinned model is accepted and request size, batch count, string lengths and vector dimensions are bounded. There are no CORS permissions.

After authentication and a successful private health check, Render may set:

```text
DUAL_LINEAGE_RAG_EMBEDDING_BACKEND=http
DUAL_LINEAGE_RAG_EMBEDDING_MODEL=Qwen3-Embedding-0.6B-Q8_0
DUAL_LINEAGE_RAG_EMBEDDING_DIMENSIONS=1024
DUAL_LINEAGE_RAG_EMBEDDING_URL=https://ayahos-node001-rag-gateway.fuaadabdullah.workers.dev/v1/embeddings
DUAL_LINEAGE_RAG_EMBEDDING_TIMEOUT_SECONDS=20
DUAL_LINEAGE_RAG_EMBEDDING_BATCH_SIZE=8
```

These variables **must not be activated** until the Worker bearer secret works end-to-end. The Cloudflare Workers VPC private service is free during its beta, but platform limits and machine availability still apply.

## Validation

```shell
node --test deploy/cloudflare/node001-rag-gateway/worker.test.mjs
```

After secure activation, require a real authenticated POST returning 1024 finite vector dimensions; an unauthenticated POST must return 401. Then verify `/v1/runtime/status`, an authenticated `/v1/rag/search` with `query_embedded=true`, correct vector ranking and a completed customer chat with citations. Existing Supabase has three curated chunks with real 1024-dimensional embeddings, but indexed vectors alone are not proof of live query embeddings.

## Rollback

Set `DUAL_LINEAGE_RAG_EMBEDDING_BACKEND=lexical` (or the previous value) on Render before changing tunnel or Worker. Leave chat inference intact. Disable the Workers subdomain, revoke its Worker `API_TOKEN`, and stop the user-level Windows scheduled tunnel task only after confirming the previous lexical RAG path is healthy.

Node 001's dedicated tunnel and CPU embedding server have per-user Windows logon tasks. They will restart on the user's next login, but do **not** provide machine-wide pre-login availability. Do not call the system fully highly available without additional proof.
