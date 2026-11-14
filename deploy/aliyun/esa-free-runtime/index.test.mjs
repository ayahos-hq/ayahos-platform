import { test } from 'node:test';
import assert from 'node:assert/strict';
import runtime, { handleRequest } from './src/index.mjs';

const SECRET = 'a-local-test-credential-only-32-bytes-or-more';
const API = 'https://goblin-dual-lineage-api.onrender.com/health';
const SITE = 'https://ayahos.pages.dev/api/build';
const origin = 'https://edge-runtime.example';
const req = (path, options) => new Request(origin + path, options);
const auth = (path) => req(path, { headers: { authorization: `Bearer ${SECRET}` } });

test('default ESA handler returns public health without credentials', async () => {
  const res = await runtime.fetch(req('/healthz'), {}, {});
  assert.equal(res.status, 200);
  assert.deepEqual((await res.json()).authority, 'none');
  assert.equal(res.headers.get('cache-control'), 'no-store');
});

test('capabilities categorically exclude policy and model inference', async () => {
  const res = await runtime.fetch(req('/v1/capabilities'), {}, {});
  const body = await res.json();
  assert.equal(body.inference, false);
  assert.equal(body.policy_authority, false);
  assert.equal(body.persistent_storage, false);
  assert.equal(body.cost_mode, 'free-required');
});

test('probes fail closed if secret not configured', async () => {
  let called = 0;
  const res = await handleRequest(auth('/v1/health/probes'), {}, async () => { called++; });
  assert.equal(res.status, 503);
  assert.equal(called, 0);
});

test('probes reject unauthorized or short token before network', async () => {
  let called = 0;
  const fetcher = async () => { called++; };
  assert.equal((await handleRequest(req('/v1/health/probes'), { PROBE_BEARER_TOKEN: SECRET }, fetcher)).status, 401);
  assert.equal((await handleRequest(req('/v1/health/probes', { headers: { authorization: 'Bearer wrong' } }), { PROBE_BEARER_TOKEN: SECRET }, fetcher)).status, 401);
  assert.equal((await handleRequest(req('/v1/health/probes', { headers: { authorization: 'Bearer x' } }), { PROBE_BEARER_TOKEN: 'x' }, fetcher)).status, 401);
  assert.equal(called, 0);
});

test('authorized probes use two fixed HTTPS targets, no credentials, no response body leakage', async () => {
  const called = [];
  const fetcher = async (url, init) => {
    called.push({ url, init });
    return new Response('private-body-never-exposed', { status: 200 });
  };
  const res = await handleRequest(auth('/v1/health/probes'), { PROBE_BEARER_TOKEN: SECRET }, fetcher);
  assert.equal(res.status, 200);
  assert.deepEqual(called.map(x => x.url), [API, SITE]);
  assert.ok(called.every(x => x.init.method === 'GET' && x.init.redirect === 'manual'));
  assert.ok(called.every(x => !new Headers(x.init.headers).has('authorization')));
  const body = await res.json();
  assert.equal(body.status, 'healthy');
  assert.equal(JSON.stringify(body).includes('private-body'), false);
});

test('one broken dependency reports degraded, with no internal error leak', async () => {
  const fetcher = async (url) => url === API ? Promise.reject(Error('secret diagnostic')) : new Response('ok', { status: 200 });
  const res = await handleRequest(auth('/v1/health/probes'), { PROBE_BEARER_TOKEN: SECRET }, fetcher);
  const body = await res.json();
  assert.equal(body.status, 'degraded');
  assert.equal(body.checks.api.ok, false);
  assert.equal(body.checks.site.ok, true);
  assert.equal(JSON.stringify(body).includes('secret diagnostic'), false);
});

test('bad path, method and query never contact external providers', async () => {
  let called = 0;
  const fetcher = async () => { called++; };
  assert.equal((await handleRequest(req('/v1/health/probes?target=evil'), { PROBE_BEARER_TOKEN: SECRET }, fetcher)).status, 400);
  assert.equal((await handleRequest(req('/v1/health/probes', { method: 'POST', body: 'bad' }), { PROBE_BEARER_TOKEN: SECRET }, fetcher)).status, 405);
  assert.equal((await handleRequest(req('/v1/proxy?target=evil'), { PROBE_BEARER_TOKEN: SECRET }, fetcher)).status, 404);
  assert.equal(called, 0);
});

test('quota errors never trigger retries or paid fallbacks', async () => {
  let called = 0;
  const fetcher = async () => { called++; return new Response('quota', { status: 503 }); };
  const res = await handleRequest(auth('/v1/health/probes'), { PROBE_BEARER_TOKEN: SECRET }, fetcher);
  assert.equal((await res.json()).status, 'degraded');
  assert.equal(called, 2);
});
