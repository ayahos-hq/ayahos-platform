// AyahOS Node 001 CPU-only embeddings gateway.
// Public Workers URL, but the origin is reachable ONLY through a bound, fixed-target VPC Service.
// The public route is fail-closed and always requires an operator-provisioned bearer secret.
export const MODEL = "Qwen3-Embedding-0.6B-Q8_0";
const DIMENSIONS = 1024;
const MAX_BODY_BYTES = 32 * 1024;
const MAX_INPUTS = 8;
const MAX_TEXT_CHARS = 4096;
const MAX_TOTAL_CHARS = 8192;
const ORIGIN = "http://127.0.0.1:8092";
const RESPONSE_HEADERS = {
  "Cache-Control": "no-store",
  "X-Content-Type-Options": "nosniff",
};

function reject(status, message) {
  return new Response(message, { status, headers: RESPONSE_HEADERS });
}

function authorized(header, key) {
  if (!key || key.length < 32 || header.length > 512) return false;
  const expected = `Bearer ${key}`;
  let different = header.length ^ expected.length;
  for (let i = 0; i < Math.max(header.length, expected.length); i++) {
    different |= (header.charCodeAt(i) || 0) ^ (expected.charCodeAt(i) || 0);
  }
  return different === 0;
}

function validatedInput(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload) || payload.model !== MODEL) return null;
  const input = typeof payload.input === "string" ? [payload.input] : payload.input;
  if (!Array.isArray(input) || input.length < 1 || input.length > MAX_INPUTS) return null;
  let chars = 0;
  for (const text of input) {
    if (typeof text !== "string" || !text.trim() || text.length > MAX_TEXT_CHARS) return null;
    chars += text.length;
  }
  if (chars > MAX_TOTAL_CHARS) return null;
  return input;
}

function validatedVector(data, inputCount) {
  if (!data || typeof data !== "object" || !Array.isArray(data.data) || data.data.length !== inputCount) return null;
  const indexed = new Map();
  for (const row of data.data) {
    if (!row || !Number.isInteger(row.index) || row.index < 0 || row.index >= inputCount || indexed.has(row.index)) return null;
    const values = row.embedding;
    if (!Array.isArray(values) || values.length !== DIMENSIONS) return null;
    let magnitude = 0;
    for (const value of values) {
      if (typeof value !== "number" || !Number.isFinite(value)) return null;
      magnitude += value * value;
    }
    if (!Number.isFinite(magnitude) || magnitude <= 0) return null;
    indexed.set(row.index, { object: "embedding", index: row.index, embedding: values });
  }
  if (indexed.size !== inputCount) return null;
  return Array.from({ length: inputCount }, (_, index) => indexed.get(index));
}

export async function handleRequest(request, env) {
  if (!env?.API_TOKEN || !env?.PRIVATE_EMBEDDER) return reject(503, "not configured");
  if (!authorized(request.headers.get("authorization") || "", env.API_TOKEN)) return reject(401, "unauthorized");

  const path = new URL(request.url).pathname;
  if (path === "/health") {
    if (request.method !== "GET") return reject(405, "method not allowed");
    try {
      const response = await env.PRIVATE_EMBEDDER.fetch(new Request(`${ORIGIN}/health`, { method: "GET" }));
      if (response.status !== 200) return reject(503, "embedding unavailable");
      const health = await response.json();
      if (health.status !== "ok") return reject(503, "embedding unavailable");
      return Response.json({ status: "ready", model: MODEL, dimensions: DIMENSIONS }, { headers: RESPONSE_HEADERS });
    } catch {
      return reject(503, "embedding unavailable");
    }
  }
  if (path !== "/v1/embeddings") return reject(404, "not found");
  if (request.method !== "POST") return reject(405, "method not allowed");

  const length = Number(request.headers.get("content-length") || "0");
  if (length > MAX_BODY_BYTES) return reject(413, "payload too large");
  if (!(request.headers.get("content-type") || "").toLowerCase().startsWith("application/json")) return reject(415, "JSON required");

  let input;
  try {
    const raw = await request.text();
    if (new TextEncoder().encode(raw).length > MAX_BODY_BYTES) return reject(413, "payload too large");
    input = validatedInput(JSON.parse(raw));
    if (!input) return reject(400, "unsupported embedding request");
  } catch {
    return reject(400, "invalid JSON");
  }

  let response;
  try {
    response = await env.PRIVATE_EMBEDDER.fetch(new Request(`${ORIGIN}/v1/embeddings`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ model: MODEL, input }),
      signal: AbortSignal.timeout(15000),
    }));
    if (response.status !== 200) return reject(502, "embedding unavailable");
    const rows = validatedVector(await response.json(), input.length);
    if (!rows) return reject(502, "invalid embedding response");
    return Response.json({ object: "list", model: MODEL, data: rows }, { headers: RESPONSE_HEADERS });
  } catch {
    return reject(502, "embedding unavailable");
  }
}

export default { fetch: handleRequest };
