# Live operational evidence collection

The live collection deployment is intentionally split into two public-facing services and one private
Supabase evidence store.

- `goblin-dual-lineage-web`: browser UI. It never receives the runtime API key or reviewer secret.
- `goblin-dual-lineage-api`: authenticated lightweight FastAPI control plane. It does not run model
  weights or ML observers; it authorizes, dispatches, and writes only consented text-free evidence.
- Supabase project `supabase-copper-island`: private Postgres evidence store. The three evidence tables
  have RLS enabled and no `anon` or `authenticated` grants. Only the server-side API receives its
  connection string through Render's `DATABASE_URL` secret.

## Review loop

1. Enable **Operational learning** before sending a real request.
2. The runtime records structured telemetry, never prompt or response text. Optional ML observation
   belongs on a separately managed research/compute worker and cannot change deterministic policy.
3. When the request reaches a terminal state, the browser shows **Human review**.
4. Confirm or edit the scenario family, task class, complexity, risk, uncertainty, and escalation
   labels. Shadow values are suggestions only.
5. Save the reviewed label. The panel immediately refreshes the promotion-readiness counts.
6. Use **Withdraw evidence** to tombstone the request and remove its observation/labels from export.

The promotion target remains the actual family-disjoint held-out split: at least 500 reviewed test
samples and 20 test scenario families with usable risk/escalation class support.

## Deployment

`render.yaml` expects the Supabase Postgres connection string as a Render secret named `DATABASE_URL`.
The deployed API sets `DUAL_LINEAGE_DATABASE_MODE=postgres`; it runs the versioned schema migrations
before startup and refuses to start against a missing or outdated schema. Local development keeps
`DUAL_LINEAGE_DATABASE_MODE=local` and may use the SQLite fallback.
The PostgreSQL Shared Spine uses the same `DATABASE_URL` by default, or an explicit
`DUAL_LINEAGE_SPINE_DATABASE_URL`. Run `python -m dual_lineage.db migrate` before startup.
`python -m dual_lineage.db retention` runs one bounded retention pass: it archives terminal
histories after 7 days and purges archived payloads 30 days after archival, then prints the counts
as JSON. Purging preserves the request's terminal state snapshot but removes replayable event
payloads. Render does not schedule or host this background job; it is reserved for the lightweight
API/control gateway. A Node 1 or separately managed cloud scheduler must invoke the command using the
private `DATABASE_URL`. A successful external invocation and live migration/retention output still
require verification.
The runtime API key authenticates internal web-to-API calls. The public Vercel chat proxy uses a separate
`GOBLIN_SITE_API_KEY` / `DUAL_LINEAGE_SITE_API_KEY` pair. Human evidence mutations add a separate
browser-session reviewer access token at the web boundary. Use Supabase's pooler session connection for
an IPv4-only Render service; keep the connection string and both API credentials server-side and never
expose them to the browser.

The API build installs the control-plane dependency set only. Model weights and provider runtimes are
not installed on Render. Workflow delivery, scheduling, and other long-running workers are also
external to Render.

Compute-plane ownership is explicit: Node 1, Oracle, AWS Bedrock, and Aliyun perform heavy model
work as horizontal peers. Render remains the control plane for API/auth/routing/registry/telemetry and
does not load model weights. Eligibility is filtered first, then rendezvous hashing elects one peer for
the request. There is no fixed Node 1 → Oracle → AWS → Aliyun order.

Consented MiniLM evidence uses a separate private shadow worker. The Render blueprint configures
`RemoteMiniLMShadowClassifier`, but the observer is active only when its HTTPS URL and bearer secret are
present and the worker is reachable. Confirm `shadow_enabled=true` and `shadow_backend=remote-minilm`
on the authenticated runtime-status surface before sending consented collection traffic. If that setup is
missing or invalid, the runtime falls back to the local, non-authoritative bootstrap observer;
**operational embedding capture is disabled**, not replaced by synthetic embeddings. The core API and
Undermind deterministic authorization remain available. The authenticated `/v1/runtime/status`
will show `shadow_backend=bootstrap` and `operational_learning_enabled=false`, while
`/v1/runtime/health` reports `status=degraded` with
`operational_learning.state=unhealthy` and
`operational_learning.error_type=EmbeddingShadowUnavailable`. This is an explicit failed learning
dependency, not a healthy off state. When `DUAL_LINEAGE_TRAINING_REQUIRED=true`, any failure to
initialize the selected trained shadow backend **still blocks startup**. Restore the private HTTPS
worker URL/credential in trusted deployment secret management, verify the worker health, and deploy
again; do not commit credentials or enable capture against an untrusted endpoint. Ordinary
non-consented shadow telemetry remains local to the deterministic bootstrap observer. Only requests carrying explicit `learning_consent=true` call the private `/v1/shadow/predict`
worker. That worker owns the MiniLM weights and linear-head artifact and returns only the shadow
prediction plus frozen embedding; Render stores that text-free evidence in the operational PostgreSQL
store. On Oracle, the public HTTPS endpoint remains the existing cognitive node agent; it authenticates
the control plane with the node-inference credential and proxies only `/v1/shadow/predict` to the loopback
worker. The worker uses a separate secret generated and retained on Oracle, so port 8120 and the worker
credential are never exposed to Render or the public network.

The migration metadata, Shared Spine, RAG (both lineages' corpora, `rag_*` and `undermind_rag_*`), and Ruby queue tables have RLS enabled with explicit deny
policies for `anon` and `authenticated`. They are private server-side stores, and the browser must
not read or mutate them through Supabase client credentials. The server-side PostgreSQL role remains
authorized.

## Remote MiniLM readiness contract

Runtime health cannot infer MiniLM readiness from the evidence store alone. The authenticated
`GET /v1/runtime/health` now checks the remote worker using this **text-free chain**:

1. The Render control plane calls the configured HTTPS node agent
   `GET /v1/shadow/health` with its existing node-inference bearer credential.
2. The node agent verifies that credential and queries its loopback worker at
   `GET /v1/shadow/ready` using the separate worker credential.
3. The worker verifies its own credential, ensures the embedding model loads, and
   returns only `{"status":"ready","embedding_capable":true}`.
4. Only if that succeeds *and* the evidence store responds is operational learning
   reported healthy. Errors are classified as `ShadowWorkerUnavailable`, never
   accompanied by raw secrets, worker URLs, or sample text.

These probes send **no user messages or embeddings**. They run under a short timeout,
do not modify Undermind authorization, and do not change the per-request consent
requirement for operational evidence.

### Recovery after compute-node outage

- Confirm the actual Oracle/Node 1 instance is running and its HTTPS node agent
  responds to its documented health route. Do not assume the example IP is current.
- On that machine, deploy the current node agent and private shadow worker; verify
  the pinned MiniLM artifact and local model cache.
- On the node only, set `DUAL_LINEAGE_NODE_SHADOW_WORKER_URL` to the loopback worker
  and `DUAL_LINEAGE_NODE_SHADOW_WORKER_SECRET` to its private worker secret.
- On Render only, configure `DUAL_LINEAGE_SHADOW_REMOTE_URL` to the *verified* HTTPS
  node-agent URL and provide the matching bearer credential through
  `DUAL_LINEAGE_SHADOW_REMOTE_SECRET` or the existing
  `DUAL_LINEAGE_NODE_INFERENCE_SECRET` fallback. Never paste these values into
  GitHub, build logs or frontend code.
- Redeploy the Render API to pick up the settings. Check authenticated
  `/v1/runtime/status` for `shadow_backend=remote-minilm` and
  `operational_learning_enabled=true`, then `/v1/runtime/health` for
  `operational_learning.state=healthy`. Finally, run one authorized
  consented test and verify the evidence count increases without storing prompt text.

Until all checks pass, continue using the local, shadow-only bootstrap observer.
The public chat does not need this worker to answer and must not inherit its outage.

## Export from Postgres

With the deployment's database URL and operational salt available in a trusted shell:

```bash
PYTHONPATH=apps/api/src python -m dual_lineage.learning.operational_cli \
  --output benchmarks/datasets/generated/operational_labeled.jsonl
make operational-readiness
```

Never copy the runtime API key, database URL, or provider credentials into browser-side environment variables.

## PostgreSQL migrations and SQLite import

Apply the canonical schema from a trusted shell before starting a shared environment:

```bash
PYTHONPATH=apps/api/src python -m dual_lineage.db migrate
PYTHONPATH=apps/api/src python -m dual_lineage.db status
```

To preserve the Python operational-learning SQLite store, import it into the already migrated
database. Ruby RAG storage is operated by `apps/rag-ruby` and does not go through this Python importer:

```bash
PYTHONPATH=apps/api/src python -m dual_lineage.db.import_sqlite \
  --database-url "$DATABASE_URL" \
  --operational-db data/operational-learning.sqlite3
```

Back up the SQLite files before import and retain them as read-only rollback archives until Postgres
row counts and persistence have been verified.


## External inference targets and operator controls

Render is the control plane, not an inference host. Node 1 (`node-001`), Oracle
(`oracle-heavy`), AWS Bedrock, and Aliyun are compute-plane peers. Each must be eligible and
separately credentialed before it can serve requests; target names are not proof of registration or
liveness.

Compute-fabric membership is discovered dynamically from the live Compute Registry and configured
cognitive provider registry. Node 1, Oracle, AWS Bedrock, and Aliyun are peers when eligible, and any
additional cognitive route that passes the same policy checks joins the same election. There is no
static membership or preference-order variable. The deterministic policy and rendezvous scheduler
remain authoritative for dispatch.

The backend runtime status endpoint uses `DUAL_LINEAGE_NODE_OPERATOR_SECRET`. The Next.js server
uses the same value as `GOBLIN_OPERATOR_SECRET` when reading operator-safe status.

The public Render deployment deliberately sets `GOBLIN_CONTROL_MUTATIONS_ENABLED=false`. This keeps
`/control` useful for status inspection without exposing permission mutation through an
unauthenticated public proxy. Enable mutations only behind an authenticated operator surface.


## Smoke-test evidence isolation

Deployment and end-to-end validation requests use reserved request ID prefixes:
`fill-`, `milestone-`, `smoke-`, and `validation-`.

Labels for those requests are stored with `label_source=smoke_test` for debugging, but readiness,
export, retraining, and promotion evidence only admit the latest `human_review` revision. This keeps
live smoke tests inspectable without allowing scripted traffic to inflate operational evidence counts.


## Automated deployment-drift recovery

The live E2E workflow treats Render rollout timing as an expected transient condition rather than an
application failure. Render exposes `RENDER_GIT_COMMIT` to both the Python API and Node web service,
so each deployment reports the exact commit it is serving.

Before inference, the workflow now waits until:

- the web service `/api/build` reports the GitHub commit under test;
- the proxied runtime status reports the same API commit;
- the governed runtime contract is healthy;
- the readiness endpoint is reachable;
- the canonical Overmind server responds on `/v1/models`.

Non-streaming and streaming smoke probes retry only transient network/gateway statuses
(`000`, `502`, `503`, `504`) with bounded attempts. A failed consented retry is immediately
withdrawn so deployment turbulence cannot accumulate unlabeled training evidence. Application-level
failures and unexpected HTTP statuses still fail the workflow instead of being hidden by retries.
