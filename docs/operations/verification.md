# Verification and Claim Discipline

This runbook defines how to prove changes and how to phrase capability claims.

For the Ruby-owned live retrieval path, use the single-command procedure in
[`live-rag-verification.md`](live-rag-verification.md). It is strict by default and keeps all
credentials in the caller's secret store.

## CI provider split

Octopus (`.octopus/`) is the primary CI. CircleCI and Codefresh are retired, `.drone.yml` is kept as
an on-demand standby, and GitHub Actions is not used. `.octopus/deployment_process.ocl` defines
eight required steps: seven lanes that run `scripts/ci/octopus_verify.sh` (`api-postgres`, `web-site`,
`ml-cpu`, `rag-postgres`, `ruby-worker`, `ruby-control` and `release-hardening`) and
`deployable-container-smoke`, which runs the Docker build/boot gate
`scripts/ci/deployable-container-smoke.sh`. The lanes call `scripts/ci/verify.sh` (`api-core`, `web`,
`ml`, `rag`, `worker`, `control`) or, for `release-hardening`, `scripts/release_gate.py`. The Octopus
process has not been live verified from this repository. Gates that
need PostgreSQL must use a disposable database, and `verify.sh` refuses a remote one unless
`CI_TEST_DATABASE_IS_DISPOSABLE=1` is set.

The former CircleCI automation is not replaced by Octopus: the nightly deep-verification pass, the
post-deploy checks on `main` (`scripts/live_e2e.sh`, `scripts/verify_public_site.sh`), the manual
production-release workflow, and the manual MiniLM training pipeline. Run the complete local prerequisite
sequence with `scripts/ci/production-release.sh`; it runs the API, web, ML, RAG, control, worker, and
release-hardening gates in order, but it does not deploy. After deployment convergence, the separate
post-deploy smoke `scripts/ci/live-release.sh` requires `LIVE_API_URL`, `LIVE_PUBLIC_SITE_URL`,
`LIVE_WEB_URL`, `LIVE_RUNTIME_API_KEY`, `LIVE_SITE_API_KEY`, and `CF_BRANCH=main` (with optional
`CF_REVISION`); `scripts/live_e2e.sh` consumes `RUNTIME_API_KEY` and may also use `BASE_URL`,
`EXPECTED_SHA`, and `RUN_TAG`; `make minilm-train` runs training. Run release checks only on `main`,
keep keys in the caller's secret store, and treat deployment and verified-live evidence as separate claims.

The Ruby scheduler's release/readiness jobs write commit-pinned JSON under
`artifacts/workflow/`. `RELEASE` and `HOLD` are evidence decisions, while
`completed` and `operational_failure` describe collection execution. Missing
live credentials are recorded explicitly as `HOLD` with `missing_credentials`;
they are not reported as an ambiguous transport failure. Credentialed records
are published by the worker to the authenticated Python endpoint
`GET /v1/runtime/release-evidence`, which the operator control surface displays.
The endpoint is reporting-only: CI and Python release policy remain
authoritative.

## Local verification ladder

### Level 0: static inspection

Use for understanding only. No “works” claim.

Evidence:

- code exists,
- configuration exists,
- test exists.

### Level 1: focused automated test

Run the smallest relevant test target.

Examples:

```bash
make api-test
make benchmark-test
make web-test
```

A passing focused test proves the covered behavior under the test environment, not the whole system.

### Level 2: repository gate

```bash
make check
```

Expected coverage:

- Ruff
- mypy
- API pytest suite
- ML dependency import smoke check
- web type-check

Record the commit SHA with the result.

### Level 3: local functional path

Run the real API/web process and exercise the user-facing path, including streaming where relevant.

Typical local start:

```bash
make api-dev
pnpm dev:web
```

The Makefile API target, `.env.example`, and the web server fallback all use port 8101. Keep those three defaults aligned when changing the local API port.

### Level 4: live smoke

For a named deployed environment verify:

- health endpoint,
- runtime status endpoint if applicable,
- authentication behavior,
- one bounded cognition request,
- terminal event/status,
- logs/metrics where available.

Record timestamp + commit SHA.

### Level 5: physical hardware E2E

Required before claiming real Node 001 GPU-backed cognition.

Evidence should include:

- node identity,
- GPU/model process,
- registration heartbeat,
- route decision selecting that node,
- request ID,
- actual provider/model,
- terminal output,
- usage/latency,
- failover behavior when intentionally unavailable.

## ML evidence ladder

### Synthetic

Useful for:

- pipeline validation,
- regression testing,
- leakage checks,
- calibration code,
- benchmark methodology.

Not sufficient for:

- operational safety claims,
- advisory promotion,
- enforcement promotion.

### Consented operational evidence

Requires:

- explicit request-level consent,
- compliant evidence capture,
- reviewed labels,
- readiness checks,
- family-disjoint evaluation where applicable,
- calibration/promotion report.

### Promotion

A promotion decision must be represented as data/code, not vibes.

Record:

- artifact version/hash,
- evidence source,
- dataset fingerprint,
- split strategy,
- calibration metrics,
- baseline comparison,
- gate results,
- exact authority change.

## Live environment checklist

For Render/Supabase/Datadog/OCI/SiliconFlow or any other external dependency:

1. verify the target still exists,
2. verify the current deployment/branch,
3. verify credentials are configured without exposing them,
4. run the smallest safe live check,
5. inspect logs/status,
6. report what was and was not proven.

## Failure language

Use precise statements.

Good:

- “API unit tests passed on commit X.”
- “Render blueprint configures service Y; live health was not checked.”
- “The MiniLM artifact cleared synthetic held-out gates but remains ineligible for advisory authority because operational evidence is required.”
- “Node registry code is implemented; no current physical node heartbeat was verified.”

Bad:

- “Everything works.”
- “Production ready.”
- “GPU inference is done” when only adapter tests passed.
- “Deployed” because a YAML file exists.
- “Safe” because a classifier scored 99% on generated cases.

## Change verification table

| Change type | Minimum proof |
| --- | --- |
| docs only | link/path integrity + architecture consistency check |
| pure Python logic | focused pytest + lint/mypy for touched module |
| policy/action authority | focused tests + full API suite + architecture/state docs |
| streaming | provider + coordinator streaming tests + client SSE tests |
| web UI | web tests/type-check + manual render path when possible |
| deployment config | syntax/build validation + live smoke before live claim |
| ML training | deterministic reproduction + provenance + held-out metrics |
| authority promotion | operational evidence + promotion gates + explicit review |
