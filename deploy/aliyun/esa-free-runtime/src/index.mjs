/**
 * An intentionally small AyahOS Alibaba ESA Functions & Pages canary.
 * No authority, user content, or inference is handled here.
 */
const API = 'https://goblin-dual-lineage-api.onrender.com/health';
const SITE = 'https://ayahos.pages.dev/api/build';
const JSON_HEADERS = Object.freeze({
  'content-type': 'application/json; charset=utf-8',
  'cache-control': 'no-store',
  'x-content-type-options': 'nosniff',
});

function json(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: JSON_HEADERS });
}

function tokenMatches(header, secret) {
  if (typeof secret !== 'string' || secret.length < 32 || secret.length > 256 || header.length > 512) {
    return false;
  }
  const expected = `Bearer ${secret}`;
  let mismatch = header.length ^ expected.length;
  for (let i = 0; i < Math.max(header.length, expected.length); i++) {
    mismatch |= (header.charCodeAt(i) || 0) ^ (expected.charCodeAt(i) || 0);
  }
  return mismatch === 0;
}

async function fixedProbe(url, fetchImpl) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 2000);
  try {
    const response = await fetchImpl(url, {
      method: 'GET',
      redirect: 'manual',
      headers: {},
      signal: controller.signal,
    });
    return { ok: response.status >= 200 && response.status < 300, status: response.status };
  } catch {
    return { ok: false, status: null };
  } finally {
    clearTimeout(timeout);
  }
}

export async function handleRequest(request, env = {}, fetchImpl = fetch) {
  const { pathname, search } = new URL(request.url);
  if (!['/healthz', '/v1/capabilities', '/v1/health/probes'].includes(pathname)) {
    return json({ error: 'not_found' }, 404);
  }
  if (request.method !== 'GET') return json({ error: 'method_not_allowed' }, 405);
  if (search) return json({ error: 'unsupported_query' }, 400);
  if (pathname === '/healthz') {
    return json({ state: 'ready', platform: 'alibaba-esa-edge', authority: 'none', role: 'independent-probe-runtime' });
  }
  if (pathname === '/v1/capabilities') {
    return json({ platform: 'alibaba-esa-edge', authority: 'none', inference: false, policy_authority: false,
      persistent_storage: false, writes: false, cost_mode: 'free-required', probes: ['api', 'site'] });
  }
  // On-demand probes consume Free account quota and send requests to existing
  // services, so never allow anonymous or unconfigured access.
  if (!env?.PROBE_BEARER_TOKEN) return json({ error: 'not_configured' }, 503);
  if (!tokenMatches(request.headers.get('authorization') || '', env.PROBE_BEARER_TOKEN)) {
    return json({ error: 'unauthorized' }, 401);
  }
  const api = await fixedProbe(API, fetchImpl);
  const site = await fixedProbe(SITE, fetchImpl);
  return json({ status: api.ok && site.ok ? 'healthy' : 'degraded', platform: 'alibaba-esa-edge',
    authority: 'none', checks: { api, site } });
}

export default {
  // ESA binds environment secrets in the third parameter, not second.
  fetch(request, _context, env) { return handleRequest(request, env); },
};
