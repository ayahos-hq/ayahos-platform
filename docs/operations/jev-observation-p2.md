# Jev P2: metadata-only Undermind shadow boundary (first slice)

**State:** experimental source + mock-transport tests on a stacked feature branch. This does not connect Jev to the live request coordinator, Shared Spine, Action Gateway, Ruby workers, deployment configuration, or production. No API key or paid service has been enabled.

## Implemented in this slice

- `JevShadowObserver.observe_preflight(request, result)` constructs a strictly allowlisted `JevSafeState` **after** the already-authoritative Python preflight result exists. It never uses prompt text, request metadata, RAG content, raw tool names or request IDs for external transmission.
- `observe_proposal(envelope, intent, decision)` derives action class and coarse-grained permission/risk flags from an existing deterministic action decision. It never makes that decision, changes it, or mints a lease.
- Disabled mode returns a typed `off` result without sending a request. Mismatched request/action correlation or >64 requested tools produce `skipped` with no outbound call.
- A typed provider failure or an unexpected exception yields a sanitized non-authoritative `unavailable` result. Cancellation propagates. No raw errors, credentials, user data or model responses are included in failure reasons.
- These observation methods are not automatically invoked. There is **no new live runtime dependency or gateway callback**.

## Security limits and semantics

The P1 `JevClient` still requires all explicit paid / outbound metadata gates and a server-held API key. **The total-spend limiter, scheduling/sample-rate gate, authorization to transmit even metadata, and authenticated Spine observation writer have not yet been implemented. Keep provider egress disabled.**

The field `explicit_permission` on the wire state is strictly a **summary of the deterministic action decision** (ALLOW or not), not an independent permission fact from Jev. A Jev answer cannot authorize work even if its reported probability is 1.0. `tool_allowlisted` describes the prior control envelope, not registry presence, pinned executor kind, runtime confirmation or one-use lease status. Until later integration handles effective intent and gateway confirmation, consider these descriptive signals only.

## Verification

Focused P1 + P2 tests have been exercised in an isolated Python 3.13 environment using source files, `httpx.MockTransport`, and a **local stand-in for selected brain contracts**: 32 tests passed in that narrow environment. This does not establish exact-repository integration correctness, Python 3.11 support, full ruff/mypy, API/PostgreSQL/pgvector Octopus acceptance, runtime cost/privacy compliance, or live TypeSafe behavior. Full CI remains required for merge.

## Next P2 slices

1. Rebase dependency on merged P1, inspect coordinator refactor PR #268, and add explicit injection at buffered/streamed preflight and effective action-proposal points **without touching deterministic policy**.
2. Add an actual content-free, versioned Shared Spine event writer with bounded event cardinality and privacy tests. Distinguish `off`, `skipped`, `observed`, and `unavailable`, preserving request correlation only internally.
3. Define paid request budget enforcement and sampling before ever enabling provider traffic. Respect the hard $0 infrastructure goal.
4. Run full PostgreSQL-backed tests, static checks, Octopus lanes, and authenticated staging only with separately configured credentials and cost approval. Roll back instantly by leaving observer unregistered or mode `off`.

Related: [Jev ADR-027](../architecture/adr-027-jev-undermind-observer.md), [P1 transport](jev-transport-p1.md).
