# AyahOS cache performance and correctness gates

Status: P0 instrumentation implemented; **no live baseline or cost savings measured** by this change.

## Baseline before and after each cache rollout

In the same workload and environment, record p50/p95 end-to-end latency,
provider request count, embedding call count, provider billed usage/cost,
cache hit/miss/store/eviction/invalidation counts, and policy-denied requests.
Identify the actual deployment SHA and sampled time window. Run a cold cache
and a warmed cache; compare with caching disabled to avoid attributing ordinary
provider variance to cache behavior.

`CacheCounters` provides bounded, content-free event counts for cache owners.
A counter snapshot is local process evidence only. It is not a cross-replica
rate, a production baseline, or proof of a cost reduction. Never export raw
cache keys, prompts, document text, user identifiers, or credentials.

## Acceptance and rollback

- Zero cross-principal hits in isolation tests.
- Zero stale reads following a successful same-process document mutation.
- Denied network/cloud use must never be authorized by a cached computation.
- Cache failure must degrade to the original uncached path.
- Preserve authentication, public rate limits, and streaming `no-store`.
- Compare miss-path latency against an uncached baseline before rollout.
- Keep cache capacity/TTL bounded and allow disabling without a migration.

Octopus is the designated CI gate. Review each Octopus task and exact SHA;
GitHub PR mergeability and synthetic replay are not substitutes for live checks.

## P1 retrieval cache

The process-local Overmind RAG cache keeps its 30-second default TTL and 128-entry
bound. Keys include query, top_k, cloud-embedding permission, embedding model ID,
and an in-process corpus generation. A successful ingest or delete advances the
generation and clears cached results. Concurrent identical searches share one
in-flight request; a caller cancellation does not cancel another reader's
request. An older search cannot fill the cache after a mutation.

Counter snapshots are process-local only, not Shared Spine events or proof of
production savings. **Cross-replica document mutations are not coordinated**:
a process-local generation does not invalidate another Render replica's cache.
For multi-replica workloads with mutable documents, disable caching using
`DUAL_LINEAGE_RAG_SEARCH_CACHE_TTL_S=0` or implement shared corpus versioning before promotion.

Set `DUAL_LINEAGE_RAG_SEARCH_CACHE_SIZE` to cap retained results. These values
are read when the API runtime is constructed; changing them requires a restart.

## P2 embedding memoization

`CachingRagEmbedder` retains only SHA-256 fingerprint keys and normalized vectors
in a bounded per-process LRU; it does not persist raw text to keys or logs.
The key includes the model ID, embedding dimensions and configured corpus scope.
A changed model or dimensions needs a new embedder instance and fresh indexing.

Local embedding caching defaults to 300 seconds and 512 entries. Remote
embedding caching defaults **off**, and can be explicitly enabled with
`DUAL_LINEAGE_RAG_EMBED_CACHE_TTL_S`. Use
`DUAL_LINEAGE_RAG_EMBED_CACHE_SIZE` for capacity. For strict multi-tenant
isolation keep the remote cache off unless the runtime has a verified
tenant-scoped wrapper. Caching never changes the mandatory `remote_allowed`
check before an embedding request or a cache lookup.

## P3 Cloudflare Pages cache policy

The public static page (`/` and `/index.html`) requests revalidation, so
deployments can update the client. Content-hashed Next assets under
`/_next/static/*` retain one-year immutable browser caching. The stable-name
logo SVG uses one-hour caching. These are **browser-facing response policies**;
Cloudflare's actual edge cache state and purge behavior must be checked in a
live Pages deployment before claiming any performance improvement.

Pages Functions preserve `no-store` by default, while live SSE replies use
`no-cache, no-transform` to prevent transformation/buffering. Do not apply
public CDN caching to `POST /api/chat`, rate-limit responses, runtime
evidence, credentials, or personalized history.

## P4 provider-native prefix reuse (Anthropic)

`DUAL_LINEAGE_ANTHROPIC_PROMPT_CACHE=true` opts a configured Anthropic route
into the provider's native, five-minute ephemeral prompt caching by adding the
documented top-level `cache_control` field to the Messages payload. Default
is **off**; unsupported OpenAI-compatible vendors receive no cache hints.
The provider retains and matches prefixes; AyahOS does not store conversation
text or cached answers. Request-supplied `cache_control` is always ignored.

Both streaming and non-streaming Anthropic usage account for uncached, cache
write, and cache read input token counts. Budgeted cost is conservatively
estimated by charging cache reads at full input price and adding the potential
25% 5-minute cache-write premium. This is **not an invoice or a measured saving**;
reconcile provider billing before enabling broadly. Do not enable for sensitive
workloads without a separate data-retention review.

References: https://platform.claude.com/docs/en/build-with-claude/prompt-caching

## P5 distributed-cache decision — deferred, not omitted

The committed Render blueprint currently declares one free-tier API service
and no shared cache service. There is no verified multi-replica workload
or measured savings that would justify Redis today. **Do not deploy Redis**
just to satisfy a checklist: it adds another dependency, credential, failover
path, and cost.

`DUAL_LINEAGE_RAG_REPLICA_COUNT` is declared as `1` for the current Render
blueprint. The runtime's `effective_search_cache_ttl` disables process-local
RAG search caching whenever the declared replica count exceeds one, unless
a future version explicitly implements safe shared invalidation. Operators
must keep this value in sync with actual deployment topology. If uncertain,
set `DUAL_LINEAGE_RAG_SEARCH_CACHE_TTL_S=0` until topology is verified.

Reconsider a distributed cache when measured traffic justifies it **and**
cross-replica consistency is required. A future design must implement
tenant isolation, content-free observability, corpus-version invalidation,
bounded retention, authentication, outage fallbacks and cost benchmarks
before shipping. No Redis service was provisioned by this PR.

### Release evidence still required

Run Octopus's required gates on the final merged SHA, verify the Render API
build and RAG unit/integration tests, and check Cloudflare production root,
versioned assets, `/api/build` and private chat responses. Confirm the
production site key exists through its secret manager; cache changes do not
repair missing production credentials. Until those checks pass, classify
these improvements as merged implementation, not verified-live deployment.

## Post-rollout in-flight read correctness

A corpus mutation can complete while a retrieval request is awaiting Ruby RAG.
The retrieval adapter now retries when its corpus generation differs from
the generation at lookup start, rather than returning a stale citation to the
caller. Retries are bounded to three attempts; repeated concurrent corpus
mutations fail explicitly instead of serving stale evidence. Coalesced readers
are counted under `coalesce`, not as additional cache misses. This invariant
is process-local; multi-replica deployments still require TTL=0 or shared
corpus-version coordination.
