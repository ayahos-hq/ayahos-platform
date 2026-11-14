import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { handleRequest } from "./worker.mjs";

const SECRET = "test-credential-not-a-real-secret-000000000000";
const MODEL = "Qwen3-Embedding-0.6B-Q8_0";
const input = ["Undermind has final policy authority."];

function vector(n = 1024) {
  return Array.from({ length: n }, (_, i) => i === 0 ? 1 : 0);
}

function request({ authorization = `Bearer ${SECRET}`, method = "POST", path = "/v1/embeddings", body = { model: MODEL, input } } = {}) {
  return new Request(`https://gateway.example${path}`, {
    method,
    headers: { authorization, "content-type": "application/json" },
    ...(method !== "GET" && method !== "HEAD" ? { body: JSON.stringify(body) } : {}),
  });
}

function gateway({ configured = true, privateStatus = 200, responseVector = vector() } = {}) {
  const record = { calls: 0, request: null };
  const env = {
    API_TOKEN: configured ? SECRET : "",
    PRIVATE_EMBEDDER: {
      async fetch(r) {
        record.calls += 1;
        record.request = r;
        if (privateStatus !== 200) return new Response("upstream failure", { status: privateStatus });
        return Response.json({
          data: [{ object: "embedding", index: 0, embedding: responseVector }],
          model: MODEL,
        });
      },
    },
  };
  return { env, record };
}

test("refuses all calls when the gateway credential is not installed", async () => {
  const { env, record } = gateway({ configured: false });
  const result = await handleRequest(request(), env);
  assert.equal(result.status, 503);
  assert.equal(record.calls, 0);
});

test("rejects missing or incorrect bearer auth without contacting private worker", async () => {
  const { env, record } = gateway();
  assert.equal((await handleRequest(request({ authorization: "" }), env)).status, 401);
  assert.equal((await handleRequest(request({ authorization: "Bearer incorrect" }), env)).status, 401);
  assert.equal(record.calls, 0);
});

test("valid request forwards to the exact private VPC host, strips external bearer credential", async () => {
  const { env, record } = gateway();
  const result = await handleRequest(request(), env);
  assert.equal(result.status, 200);
  const payload = await result.json();
  assert.equal(payload.data[0].embedding.length, 1024);
  assert.equal(record.calls, 1);
  assert.equal(new URL(record.request.url).pathname, "/v1/embeddings");
  assert.equal(new URL(record.request.url).hostname, "127.0.0.1");
  assert.equal(record.request.headers.has("authorization"), false);
  const forwarded = await record.request.json();
  assert.deepEqual(forwarded, { model: MODEL, input });
});

test("disallows arbitrary paths, methods, models, and oversized payloads", async () => {
  const { env, record } = gateway();
  assert.equal((await handleRequest(request({ path: "/v1/chat/completions" }), env)).status, 404);
  assert.equal((await handleRequest(request({ method: "GET", path: "/v1/embeddings" }), env)).status, 405);
  assert.equal((await handleRequest(request({ body: { model: "other-model", input } }), env)).status, 400);
  assert.equal((await handleRequest(request({ body: { model: MODEL, input: ["x".repeat(4100)] } }), env)).status, 400);
  assert.equal(record.calls, 0);
});

test("malformed vector, wrong dimension, and upstream errors fail closed", async () => {
  for (const opts of [{ responseVector: vector(16) }, { responseVector: [NaN, ...vector().slice(1)] }, { privateStatus: 503 }]) {
    const { env } = gateway(opts);
    const res = await handleRequest(request(), env);
    assert.equal(res.status, 502);
    assert.equal((await res.text()).includes("upstream failure"), false);
  }
});

test("preflight OPTIONS is not an unauthenticated CORS proxy", async () => {
  const { env } = gateway();
  const res = await handleRequest(new Request("https://gateway.example/v1/embeddings", { method: "OPTIONS" }), env);
  assert.equal(res.status, 401);
  assert.equal(res.headers.has("access-control-allow-origin"), false);
});

test("production wrangler configuration never enables an unauthenticated worker URL by default", () => {
  const wrangler = JSON.parse(readFileSync(new URL("./wrangler.jsonc", import.meta.url), "utf8"));
  assert.equal(wrangler.workers_dev, false);
  assert.equal(wrangler.vpc_services[0].binding, "PRIVATE_EMBEDDER");
});
