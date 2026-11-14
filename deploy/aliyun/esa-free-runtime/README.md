# AyahOS Alibaba Cloud ESA Free Runtime

## Purpose and safety boundary

This is a **separate, stateless JavaScript edge runtime** on Alibaba Cloud Edge Security Acceleration (ESA) Functions & Pages. The first deployable workload is an independent, read-only availability sentinel. It proves that Alibaba Cloud, not Render, executes an AyahOS workload without migrating or duplicating the authoritative FastAPI runtime.

- `GET /healthz`: responds on the Alibaba ESA edge; does not call Render or any model.
- `GET /v1/capabilities`: explicit no inference, no policy authority, no persistence, no writes.
- `GET /v1/health/probes`: **disabled by default**, requiring a 32+ character `PROBE_BEARER_TOKEN` configured as an encrypted ESA Function variable and a matching `Authorization: Bearer ...` header. When authorized, makes at most two direct GETs to fixed public URLs: Render `/health` and Cloudflare Pages `/api/build`. Returns status codes/booleans only, not response bodies or credentials. Runs **only when requested**; no scheduled polling or paid dependencies.
- All other paths return 404, non-GET requests 405, and queries 400. No arbitrary upstream URL or proxy functionality.

**This does not move Overmind, Undermind, PostgreSQL, provider keys, or model inference.** Render remains primary. ESA cannot directly host the current full Python/Ruby AyahOS application: its Free Edge Function runtime executes JavaScript and has strict execution/subrequest limits. Do not implement a second Undermind policy authority.

## International Alibaba Cloud ESA console

Use the **international console**: https://esa.console.alibabacloud.com/ (redirects to https://account.alibabacloud.com/ for sign-in). **Do not use** `https://esa.console.aliyun.com/`, which leads to the separate Chinese Alibaba Cloud account realm and cannot be assumed to have the same subscriptions or credentials. The international console link is confirmed by the official Alibaba Cloud English ESA billing documentation.

## Genuine $0 constraints (verified 2026-10-23)

Alibaba's ESA **Functions & Pages Free mode** allows **100,000 requests/account/day**, **20 functions**, **5 versions per function**, and **1,000 network-wide concurrent requests per function**. Once quota is exhausted, ESA returns HTTP 503 until daily reset, rather than upgrading to paid mode. There is **no SLA** and limited log delivery. The ESA Entrance plan is $0/month, but features outside Free functions, such as certain data services or paid add-ons, may incur costs.

**Never confuse this with Alibaba Function Compute (FC).** FC's new-user trial is time-limited to three consecutive months, and overruns are pay-as-you-go, so FC does not meet AyahOS's durable zero-spend requirement.

Before *any* ESA deployment, verify in the actual Alibaba account console that Edge Computing > Functions & Pages is set to **Free**. Do not select `Paid`, activate separately billed products, purchase resources, turn on Edge KV, change domain nameservers, or move Cloudflare Pages traffic. A DashScope Model Studio API key is **not** an ESA deployment credential.

## Local verification

From `deploy/aliyun/esa-free-runtime`:

```sh
node --test index.test.mjs
node --check src/index.mjs
npx --yes esa-cli@1.0.13 dev
```

The first commands need only Node 20+; there are no runtime npm dependencies. The public `/healthz` and `/v1/capabilities` paths need no secret. Do not configure `PROBE_BEARER_TOKEN` until a secure ESA variable and a legitimate operator caller are provisioned. `esa-cli dev` simulates the Alibaba edge; no cloud authentication is required. In another shell, verify:

```sh
curl -fsS http://127.0.0.1:18080/healthz
curl -fsS http://127.0.0.1:18080/v1/capabilities
```

## Free-only release stages

1. **Account check:** Log in to Alibaba Cloud ESA console and verify Functions & Pages is active and in **Free** mode. Confirm no paid features are enabled.
2. **Least-privilege CLI session:** Use `npx esa-cli@1.0.13 login` with an ESA-scoped RAM credential on the operator's own machine, or an approved authenticated console session. **Never paste/access-control tokens into GitHub, chat, or logs.** `esa-cli` stores local credentials privately. Do not reuse `DASHSCOPE_API_KEY`.
3. **Read-only inventory:** `npx esa-cli@1.0.13 project list`. Verify name `ayahos-esa-runtime` doesn't conflict with existing user-managed projects, and that free project slots remain.
4. **Staging only:** `npx esa-cli@1.0.13 deploy --environment staging --no-preview`. Inspect the returned deployment status via `deployments list`. Free mode must be verified **before** executing this step. The standalone canary has no secrets.
5. **Live proof:** Use the provider's authenticated staging preview to verify `/healthz`, `/v1/capabilities`, and two bounded health probes. The public preview URL/token, if generated, may be short-lived; never treat it as a permanent endpoint.
6. **Production promotion:** Only after staging is proven and user account's Free mode is confirmed, deploy the tested ESA version to production. Keep the existing Cloudflare/Render paths intact, do not reroute user traffic, and do not enable paid usage automatically.
7. **Evidence:** Record Alibaba account Free mode, function name, environment, version, deployment status, one real HTTPS health response, response time, daily quota monitoring and no unexpected billing.
8. **Rollback:** Remove or disable only this optional ESA function/deployment. Do not alter Render, Cloudflare, Undermind, Supabase, or Aliyun's existing model-inference provider.

## Verification and future expansion

This initial footprint is intentionally limited so an independent, genuinely free Alibaba runtime can be proven without allocating a second API server. Once live and measurable, consider moving **only short, stateless, non-authoritative JavaScript utility operations** from existing AyahOS code, one at a time, with new tests, strict request budgets, rollout controls, content-free telemetry and E2E benchmarks demonstrating actual value. Avoid duplicating established routing or policy code simply to use capacity.

Current state: repository scaffold and local Node tests prepared. **No Alibaba ESA account auth, live activation, billing mode or deployed service has been verified yet.**

## Official references

- https://www.alibabacloud.com/help/en/edge-security-acceleration/esa/user-guide/functions-and-pages-billing
- https://www.alibabacloud.com/help/en/edge-security-acceleration/esa/user-guide/what-is-functions-and-pages/
- https://www.alibabacloud.com/help/en/edge-security-acceleration/esa/user-guide/functions-and-pages-cli-tool
- https://github.com/aliyun/alibabacloud-esa-cli/blob/master/docs/Config_en.md
- https://www.alibabacloud.com/help/en/functioncompute/trial-quota-1
