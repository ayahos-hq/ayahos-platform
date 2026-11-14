# Runtime evidence: operator-only inspection

Public chat displays answers and a thinking state. It does **not** render the
request ID, provider, model, route, preflight decision, or a runtime evidence panel.
The server-side Dual-Lineage coordinator still writes structured Shared Spine events
for each request that reaches the authenticated runtime. The public site logs a
request ID with outcome/latency metadata for troubleshooting; no prompt or answer
text is added to those diagnostic log entries by this change.

## Inspect a customer request

1. Find the `request_id` of a public chat attempt in authorized server logs.
2. Open the operator/admin web app and enter that ID in **Request ID**.
3. Enter the configured `GOBLIN_REVIEW_ACCESS_TOKEN` in **Reviewer access**.
4. Select **Inspect trace**. The existing Inspector displays the stored state,
   model/route, budgets, authority decisions, and Shared Spine timeline.

The `GET /api/cognition/:requestId/trace` proxy verifies reviewer access
before forwarding the lookup to the runtime with its server-side key. An
authenticated CI request may use the separate runtime credential; a request ID
prefix alone never grants permission. The reviewer token is held in the page's
current state, not saved by the trace lookup to localStorage or sent to the
runtime provider. Traces are unavailable if the backend has not recorded the
request, storage is offline, or retention has purged the evidence.

## Customer storage and accessibility

Legacy `runtimeEvidence` entries are scrubbed from customer chat localStorage
on read/write; message content and retry/edit behavior are preserved.
The thinking logo rotates for the active public response until completion and
text is buffered until the final event; interruption exposes a retained partial
answer if available. When the device requests reduced motion, rotation is
disabled and the visible **Thinking** label remains as the status indication.

## Verification

The public/site response-text and conversation-store tests cover complete
message buffering and private storage migration. Admin trace route tests cover
unauthenticated smoke IDs, invalid IDs and reviewer-authorized lookup.
The full Octopus gate set, deployment and live browser E2E must pass before
claiming release readiness.

## Recorded policy outcome codes

An authenticated Shared Spine trace now stores bounded policy outcome reason
codes on the deterministic Undermind preflight event. The authorized Inspector
renders these alongside the policy version, model and routing evidence.
No reason codes recorded is not proof that every possible rule ran.
The public proxy removes private runtime identifiers and raw resilience traces;
customer chat storage continues to scrub provenance fields.
