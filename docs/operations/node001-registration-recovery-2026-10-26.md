# Node 001 registration recovery and Render upstream 503 (2026-10-26 UTC)

## Live findings

- Node 001 runs on the connected Windows workstation. `GET /health` at
  `http://127.0.0.1:8110` returned HTTP 200 with the current cognitive
  model `qwen35-9b-raw` and `backend=reachable`.
- The configured controller is
  `https://goblin-dual-lineage-api.onrender.com`.
- Direct unauthenticated `GET /health` and `GET /healthz` returned HTTP 503
  at the Render/Cloudflare edge; follow-up exploratory GET requests received
  HTTP 429. The agent independently logged intermittent HTTP 503 plus
  connection timeouts.
- The node's authenticated heartbeat therefore cannot prove registration.
  The upstream Render service may be sleeping, suspended, experiencing an
  edge/platform incident, or unhealthy behind its gateway. **No exact cause
  can be distinguished from public HTTP status alone.**
- Credentials were not changed, printed, exposed or rotated. HTTP 503
  occurs before registration identity can be independently verified.

## Implemented in this branch

1. Keep the existing authenticated POST payload, deterministic registry,
   inference allowlist, registration token, backend URL and public endpoint
   unchanged. There is **no fallback to an unauthorized controller**.
2. Track consecutive registration failures and sanitized HTTP status locally;
   preserve existing `/health.registration` payload compatibility.
3. Expose `/health.registration_state` with
   `pending|registered|degraded|auth_failed|disabled` and a
   bounded failure count, without secrets.
4. Add `GET /ready` returning HTTP 503 until registered, backend-reachable,
   and not draining. Liveness remains separate from readiness.
5. Bound retries: first retry at the normal heartbeat interval, then
   exponential delays up to 180 seconds on transient 5xx or connection
   errors; 401/403 delay 300 seconds to avoid hammering invalid credentials.
   A successful heartbeat resets failures and returns to normal cadence.

## Operational restore procedure (not completed by this source-only PR)

1. In the authorized Render workspace, inspect
   `goblin-dual-lineage-api` service status, runtime logs, suspension
   reason, free-tier allowances, current deployed commit, and health checks.
   Restore **the existing** service if eligible without upgrading tiers.
   Do not add a second control-plane or grant new credentials just to avoid
   a failing health check.
2. Verify controller `GET /health` returns 200 (not 503) consistently,
   and that its running revision serves `POST /compute/nodes/heartbeat`.
3. Verify the current registration secret matches securely on both sides
   and the public node endpoint satisfies the canonical endpoint allowlist.
   Never paste secrets into CI logs or browser consoles.
4. With the Node Agent updated through its existing supervised deployment
   process, check `GET /health` for `registration_state=registered`,
   `backend=reachable` and `GET /ready` for 200.
5. Confirm the central registry lists node-001, fresh heartbeat timestamp,
   cognitive role and approved model. Run a bounded authenticated inference
   request and failover test, then check Octopus release provenance.
6. If anything fails, keep existing inference endpoints and models unchanged;
   revert agent source to the previously pinned build. No DB migration required.

## Limits and release authority

This code cannot restart a suspended Render service and does not assert
that the 503 is resolved. The local 200 liveness is not evidence of a
registered cloud node. Integrate into the running supervisor only after
full source tests, an independent review and an authorized deployment.
The existing Octopus controller, Undermind policy and Shared Spine remain
authoritative.
