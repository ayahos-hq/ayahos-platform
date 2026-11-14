# Jev transport P1 — isolated client, not deployed

Status: **experimental implementation** on feature branch; **not merged or connected to live cognition**. Built above [ADR-027](../architecture/adr-027-jev-undermind-observer.md). No runtime uses this adapter, and no provider key has been added to a service.

## Narrow deliverable

- `brains/undermind/jev/contracts.py`: strict, frozen, extra-forbidden Pydantic objects. `JevSafeState` permits only fixed operational flags, action class and bounded counts: **no prompts, RAG notes, tool arguments, identifiers, raw user text or secrets**. Caller data outside the allowlist is rejected.
- `brains/undermind/jev/client.py`: async HTTP transport using already-declared `httpx` dependency; fixed TypeSafe `POST https://api.typesafe.ai/v1/systemone` endpoint and pinned `jev-1.14.0`. Two static `noul` questions return non-authoritative numeric observations. Strict typed response, exact model-version check, no redirects, no environment proxy, bounded request and streamed response size, bounded latency, sanitized errors, zero implicit retries.
- `brains/undermind/jev/__init__.py`: isolated import surface. No injection into `coordinator`, `policy`, `ActionGateway`, `SharedSpine`, or API endpoints.
- `tests/test_jev_p1_adapter.py`: zero-network gate tests, payload allowlist, version and response validation, HTTP failures, limits and credential redaction.

TypeSafe reference: https://docs.typesafe.ai/api/system-one and https://docs.typesafe.ai/models. Version and question semantics are **assumptions to independently verify with a credentialed staging test** before operational usage; tests use injected `httpx.MockTransport`.

## Cost and privacy gate

`JevSettings()` is `off`. Evaluation returns `None` **before creating an HTTP client** unless all of the following are set explicitly in a trusted server-side composition root:

1. `mode=JevMode.SHADOW`
2. `allow_metadata_egress=True`
3. `allow_paid_requests=True`
4. A nonempty `SecretStr` provider key

Do not expose these settings to clients, logs, generated site builds or Ruby jobs. No auto-read of environment variables or untrusted client flags is implemented in P1. The model's claimed calibration, response contents and numeric signals do not authorize or block tools.

**There is not yet a distributed spending counter, concurrency limiter or provable monthly cost cap.** Enabling paid traffic would be contrary to the current $0 requirement. Keep the adapter disconnected; implement budget enforcement and operator approval before any staging canary. No key or TypeSafe account action is needed for P1.

## Validation and future work

Local isolated module tests were run with Python 3.13, pytest, Pydantic and httpx in a temporary test package: **25 passed**. This is a focused adapter test, **not the full repository's Octopus, PostgreSQL/pgvector, mypy, Python 3.11, deployed API, or live TypeSafe validation**. Full integrated CI is still required before merging.

P2 must reconcile any coordinator refactor (draft PR #268), implement privacy-approved request/proposal metadata construction inside Python, append content-free Shared Spine evidence, enforce sampling and paid usage ceilings, and prove `off` behavior cannot change policy or gateway decisions. Ruby operations remain out of the authority path.
