# Jev P3: redacted Shared Spine evidence — first slice

**Status: isolated source and contract tests on feature branch; not a live Shared Spine event, operator feature or deployment.** The predecessor P0/P1/P2 PRs (#269, #271, #272) are merged. No provider key, paid request or operational Jev observation has been enabled.

## Evidence contract

`JevEvidenceRecord` is a frozen, extra-field-forbidden Pydantic model with `event_type=undermind.jev_observation` and `schema_version=1`, intended as the **payload for a future authenticated Shared Spine adapter**. The request identifier and event sequence are supplied by the Spine itself, not by or to TypeSafe. It permits only stage, provider model ID, observed/off/skipped/unavailable status, numeric risk/review probabilities, token counts, bounded latency, deterministic authority and one fixed reason code. It never contains raw user messages, tool names, arguments, RAG notes, secrets or provider error text.

The `jev_evidence` mapper enforces complete measurements for an `observed` record and refuses stage mismatches, dangling observations on failed/off outcomes, NaN/Inf, unexpected fields, unsupported versions, and alternative authority strings. Neither P3 evidence nor earlier Jev observations can modify `ControlEnvelope`, policy or `ActionGateway`.

## Verification and limitations

An isolated local P1+P2 test suite (32 tests) and an additional P3 evidence schema smoke were run against Python 3.13 and local copies of the changed modules. **This is not an exact-checkout full regression suite**; Octopus's API/PostgreSQL, RAG/pgvector, Ruby, web, ML and release gates remain unverified, and the new repository P3 test file has not run in that integrated environment.

## Remaining P3 work

A future PR must add a typed `EventKind.JEV_OBSERVATION` and an authenticated `SharedSpine.record_jev_observation` adapter, run the Python source-of-truth API contract generator (`make ruby-client`), verify `make ruby-client-check`, ensure the reducer and PostgreSQL event store replay the new kind, test bounded retention and terminal-request rejection, and prove schema backward compatibility with the generated Ruby client. **Do not publish the P3 record via ad hoc labels or abuse an existing critic/shadow event kind**, and do not register the provider in live request processing before hard $0 spending and explicit outbound-metadata authorization are satisfied.
