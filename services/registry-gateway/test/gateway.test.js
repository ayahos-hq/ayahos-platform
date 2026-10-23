'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const handler = require('../api/registry');
const KEY = 'test-fixture-is-not-a-real-secret-abcdefghijklmnopqrstuvwxyz';
function request(method='POST', headers={}, body={searchString:'AyahOS'}) {
  return {method, headers, body, url:'/api/registry'};
}
function response() {
  return {
    code:0, result:null, headers:{},
    setHeader(k,v){this.headers[k]=v;return this;},
    status(v){this.code=v;return this;},
    json(v){this.result=v;return this;},
  };
}
test('fails closed without a secret or valid bearer', async () => {
  delete process.env.AYAHOS_REGISTRY_GATEWAY_KEY;
  let res=response();await handler(request(),res);assert.equal(res.code,503);
  process.env.AYAHOS_REGISTRY_GATEWAY_KEY=KEY;
  res=response();await handler(request(),res);assert.equal(res.code,401);
});
test('requires POST and valid search body', async () => {
  process.env.AYAHOS_REGISTRY_GATEWAY_KEY=KEY;
  let res=response();await handler(request('GET'),res);assert.equal(res.code,405);
  res=response();await handler(request('POST',{authorization:'Bearer '+KEY},{url:'https://example.com'}),res);assert.equal(res.code,400);
});
test('does not exchange Google tokens without Vercel OIDC', async () => {
  process.env.AYAHOS_REGISTRY_GATEWAY_KEY=KEY;
  const res=response();await handler(request('POST',{authorization:'Bearer '+KEY}),res);
  assert.equal(res.code,503); assert.equal(res.result.error,'workload_identity_unavailable');
});
test('only forwards an authenticated read-only registry search', async () => {
  process.env.AYAHOS_REGISTRY_GATEWAY_KEY=KEY;
  const previous=global.fetch;const calls=[];
  global.fetch=async (url,opt)=>{
    calls.push({url,opt});
    if(url.includes('sts.googleapis.com'))return {ok:true,text:async()=>JSON.stringify({access_token:'sts-test'})};
    if(url.includes('iamcredentials.googleapis.com'))return {ok:true,text:async()=>JSON.stringify({accessToken:'google-test'})};
    return {ok:true,text:async()=>JSON.stringify({agents:[{displayName:'AyahOS Cognition Canary'}]})};
  };
  try {
    const res=response();await handler(request('POST',{authorization:'Bearer '+KEY,'x-vercel-oidc-token':'eyJ.test.token'}),res);
    assert.equal(res.code,200);assert.equal(res.result.agents.length,1);
    assert.equal(calls.length,3);
    assert.equal(calls[2].opt.headers.Authorization,'Bearer google-test');
  } finally {global.fetch=previous;}
});
test('sanitizes STS errors without returning credentials',async()=>{
  process.env.AYAHOS_REGISTRY_GATEWAY_KEY=KEY;
  const previous=global.fetch;global.fetch=async()=>({ok:false,status:403});
  try {
    const res=response();await handler(request('POST',{authorization:'Bearer '+KEY,'x-vercel-oidc-token':'eyJ.test.token'}),res);
    assert.equal(res.code,502);assert.deepEqual(res.result,{error:'workload_identity_exchange_failed'});
  } finally {global.fetch=previous;}
});

test('uses broad STS scope only for impersonation and narrow scope for registry', async () => {
  process.env.AYAHOS_REGISTRY_GATEWAY_KEY=KEY;
  const previous=global.fetch;const calls=[];
  global.fetch=async (url,opt)=>{
    calls.push({url,opt});
    if(url.includes('sts.googleapis.com'))return {ok:true,text:async()=>JSON.stringify({access_token:'sts-test'})};
    if(url.includes('iamcredentials.googleapis.com'))return {ok:true,text:async()=>JSON.stringify({accessToken:'google-test'})};
    return {ok:true,text:async()=>JSON.stringify({agents:[]})};
  };
  try {
    const res=response();
    await handler(request('POST',{authorization:'Bearer '+KEY,'x-vercel-oidc-token':'eyJ.test.token'}),res);
    assert.equal(res.code,200);
    assert.equal(calls.length,3);
    const params=new URLSearchParams(calls[0].opt.body);
    assert.equal(params.get('scope'),'https://www.googleapis.com/auth/cloud-platform');
    const body=JSON.parse(calls[1].opt.body);
    assert.deepEqual(body.scope,['https://www.googleapis.com/auth/agentregistry.read-only']);
  } finally {global.fetch=previous;}
});

test('caps upstream streaming response at 1 MiB before buffering it', async () => {
  process.env.AYAHOS_REGISTRY_GATEWAY_KEY = KEY;
  const previous = global.fetch;
  let reads = 0, cancelled = false;
  global.fetch = async () => ({
    ok: true,
    headers: { get: () => null },
    body: { getReader() { return {
      async read() { reads++; return { done: false, value: new Uint8Array(600 * 1024) }; },
      async cancel() { cancelled = true; },
      releaseLock() {},
    }; } },
    text: async () => { throw new Error('unbounded text read'); },
  });
  try {
    const res = response();
    await handler(request('POST', { authorization: 'Bearer '+KEY, 'x-vercel-oidc-token': 'eyJ.test.token' }), res);
    assert.equal(res.code, 502);
    assert.deepEqual(res.result, { error: 'workload_identity_exchange_failed' });
    assert.equal(reads, 2);
    assert.equal(cancelled, true);
  } finally { global.fetch = previous; }
});
