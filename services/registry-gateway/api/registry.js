'use strict';

const { timingSafeEqual } = require('node:crypto');

const PROJECT = 'project-eec9b975-b6bd-4b41-bad';
const PROJECT_NUMBER = '1086186141421';
const SERVICE_ACCOUNT = 'ayahos-registry-reader@project-eec9b975-b6bd-4b41-bad.iam.gserviceaccount.com';
const AUDIENCE = '//iam.googleapis.com/projects/1086186141421/locations/global/workloadIdentityPools/ayahos-vercel/providers/gateway-production';
const SEARCH_PATH = '/v1/projects/project-eec9b975-b6bd-4b41-bad/locations/global/agents:search';
const SCOPE = 'https://www.googleapis.com/auth/cloud-platform.read-only';

function bearerMatches(value, secret) {
  if (typeof value !== 'string' || typeof secret !== 'string' || secret.length < 32) return false;
  const a = Buffer.from(value);
  const b = Buffer.from('Bearer ' + secret);
  return a.length === b.length && timingSafeEqual(a, b);
}

function validSearchBody(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return false;
  if (Object.keys(body).some((key) => !['searchString', 'pageSize', 'pageToken'].includes(key))) return false;
  if (body.searchString !== undefined && (typeof body.searchString !== 'string' || body.searchString.length > 256)) return false;
  if (body.pageSize !== undefined && (!Number.isInteger(body.pageSize) || body.pageSize < 1 || body.pageSize > 100)) return false;
  if (body.pageToken !== undefined && (typeof body.pageToken !== 'string' || body.pageToken.length > 2048)) return false;
  return true;
}

async function postGoogleJson(url, headers, body) {
  const response = await fetch(url, {
    method: 'POST',
    redirect: 'error',
    signal: AbortSignal.timeout(6500),
    headers,
    body,
  });
  if (!response.ok) return null;
  const raw = await response.text();
  if (raw.length > 1048576) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  if (req.method !== 'POST') return res.status(405).json({ error: 'method_not_allowed' });

  const key = process.env.AYAHOS_REGISTRY_GATEWAY_KEY;
  if (typeof key !== 'string' || key.length < 32) return res.status(503).json({ error: 'gateway_not_configured' });
  if (!bearerMatches(req.headers.authorization, key)) return res.status(401).json({ error: 'unauthorized' });

  const path = String(req.url || '').split('?')[0];
  if (path !== SEARCH_PATH && path !== '/api/registry') return res.status(404).json({ error: 'not_found' });
  let body = req.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch { body = null; }
  }
  if (!validSearchBody(body)) return res.status(400).json({ error: 'invalid_search_request' });

  // Vercel injects the short-lived OIDC token into Node Function requests.
  // Google verifies issuer, audience, and an exact project/environment subject.
  const oidc = req.headers['x-vercel-oidc-token'];
  if (typeof oidc !== 'string' || !oidc.startsWith('eyJ') || oidc.length > 10000) {
    return res.status(503).json({ error: 'workload_identity_unavailable' });
  }
  try {
    const exchange = new URLSearchParams({
      audience: AUDIENCE,
      grant_type: 'urn:ietf:params:oauth:grant-type:token-exchange',
      requested_token_type: 'urn:ietf:params:oauth:token-type:access_token',
      subject_token_type: 'urn:ietf:params:oauth:token-type:jwt',
      subject_token: oidc,
      scope: SCOPE,
    });
    const sts = await postGoogleJson('https://sts.googleapis.com/v1/token', {
      'Content-Type': 'application/x-www-form-urlencoded',
    }, exchange.toString());
    if (!sts || typeof sts.access_token !== 'string') return res.status(502).json({ error: 'workload_identity_exchange_failed' });

    const google = await postGoogleJson(
      'https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/' + encodeURIComponent(SERVICE_ACCOUNT) + ':generateAccessToken',
      { Authorization: 'Bearer ' + sts.access_token, 'Content-Type': 'application/json' },
      JSON.stringify({ scope: [SCOPE], lifetime: '600s' }),
    );
    if (!google || typeof google.accessToken !== 'string') return res.status(502).json({ error: 'workload_identity_impersonation_failed' });

    const registry = await postGoogleJson(
      'https://agentregistry.googleapis.com' + SEARCH_PATH,
      { Authorization: 'Bearer ' + google.accessToken, 'Content-Type': 'application/json' },
      JSON.stringify(body),
    );
    if (!registry || !Array.isArray(registry.agents || [])) return res.status(502).json({ error: 'registry_search_failed' });
    return res.status(200).json({
      agents: registry.agents || [],
      nextPageToken: typeof registry.nextPageToken === 'string' ? registry.nextPageToken : '',
    });
  } catch {
    return res.status(502).json({ error: 'registry_gateway_unavailable' });
  }
}

module.exports = handler;
module.exports.bearerMatches = bearerMatches;
module.exports.validSearchBody = validSearchBody;
