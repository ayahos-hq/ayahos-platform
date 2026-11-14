import {test} from "node:test";
import assert from "node:assert/strict";
import {canonicalHead, normalizeBridgeState, relayOne, statusPayload} from "../octopus_status_relay.mjs";
const SHA = "a".repeat(40), OTHER = "b".repeat(40);
const repo = "fuaadabdullah/AyahOS_Dual_Lineage";
const pr = {head:{sha:SHA,repo:{full_name:repo}}};

test("only same-repo pull request heads qualify", () => {
  assert.equal(canonicalHead(pr,repo), true);
  assert.equal(canonicalHead({head:{sha:SHA,repo:{full_name:"attacker/fork"}}},repo), false);
  assert.equal(canonicalHead({head:{sha:"HEAD",repo:{full_name:repo}}},repo), false);
});
test("unknown, forged or malformed results never pass", () => {
  assert.equal(normalizeBridgeState({state:"success"}), "success");
  for (const obj of [null,{}, {state:"Succeeded"}, {state:"passed"},{state:42}])
    assert.equal(normalizeBridgeState(obj), null);
});
test("terminal failure is relayed to the matching SHA only", async () => {
  const calls=[];
  const fetcher=async (url,opts={})=>{
    calls.push({url,method:opts.method});
    if (url.endsWith("/status/"+SHA)) return new Response(JSON.stringify({sha:SHA,state:"failure"}),{status:200});
    if (url.endsWith("/commits/"+SHA+"/status")) return new Response(JSON.stringify({statuses:[]}),{status:200});
    if (url.endsWith("/statuses/"+SHA)) {
      const body=JSON.parse(opts.body);
      assert.equal(body.state,"failure");assert.equal(body.context,"octopus/verify");
      return new Response("{}",{status:201});
    }
    throw Error("unexpected URL");
  };
  const result=await relayOne({repository:repo,token:"ephemeral-test-token",sha:SHA,fetcher});
  assert.equal(result.outcome,"updated");assert.equal(calls.length,3);
});
test("a historical green status must not suppress the newest verdict", async () => {
  let posted = false;
  const fetcher = async (url, opts={}) => {
    if (url.endsWith("/status/"+SHA))
      return new Response(JSON.stringify({sha:SHA,state:"success"}),{status:200});
    if (url.endsWith("/commits/"+SHA+"/status"))
      return new Response(JSON.stringify({statuses:[
        {context:"octopus/verify",state:"failure"},
        {context:"octopus/verify",state:"success"},
      ]}),{status:200});
    if (url.endsWith("/statuses/"+SHA)) {
      posted = true;
      assert.equal(JSON.parse(opts.body).state,"success");
      return new Response("{}",{status:201});
    }
    throw Error("unexpected request");
  };
  const result = await relayOne({repository:repo,token:"ephemeral",sha:SHA,fetcher});
  assert.equal(result.outcome,"updated");
  assert.equal(posted,true);
});

test("missing bridge record is only pending and cannot become success", async () => {
  const calls=[];
  const fetcher=async (url,opts={})=>{
    calls.push({url,method:opts.method});
    if (url.endsWith("/status/"+SHA)) return new Response("",{status:404});
    if (url.endsWith("/commits/"+SHA+"/status")) return new Response(JSON.stringify({statuses:[]}),{status:200});
    if (url.endsWith("/statuses/"+SHA)) {assert.equal(JSON.parse(opts.body).state,"pending");return new Response("{}",{status:201});}
    throw Error("unexpected URL");
  };
  assert.deepEqual((await relayOne({repository:repo,token:"ephemeral",sha:SHA,fetcher})).state,"pending");
});
test("terminal verdict stays terminal when bridge result expires", async () => {
  const posted=[];
  const fetcher=async (url,opts={})=>{
    if (url.endsWith("/status/"+SHA)) return new Response("",{status:404});
    if (url.endsWith("/commits/"+SHA+"/status"))
      return new Response(JSON.stringify({statuses:[{context:"octopus/verify",state:"success"}]}),{status:200});
    if (url.endsWith("/statuses/"+SHA)) {posted.push(JSON.parse(opts.body));return new Response("{}",{status:201});}
    throw Error("unexpected request");
  };
  const result=await relayOne({repository:repo,token:"ephemeral",sha:SHA,fetcher});
  assert.equal(result.outcome,"unchanged");
  assert.equal(result.state,"success");
  assert.equal(posted.length,0);
});

test("bridge cannot report a successful verdict for the wrong SHA", async () => {
  let calls=0;
  const fetcher=async (url)=>{
    calls++;
    if (url.endsWith("/status/"+SHA))
      return new Response(JSON.stringify({sha:OTHER,state:"success"}),{status:200});
    throw Error("mismatched bridge result must not call GitHub");
  };
  const result=await relayOne({repository:repo,token:"ephemeral",sha:SHA,fetcher});
  assert.equal(result.outcome,"bridge_unavailable");
  assert.equal(calls,1);
});

test("pending bridge state cannot downgrade an already successful verification", async () => {
  const posted=[];
  const fetcher=async (url,opts={})=>{
    if (url.endsWith("/status/"+SHA))
      return new Response(JSON.stringify({sha:SHA,state:"pending"}),{status:200});
    if (url.endsWith("/commits/"+SHA+"/status"))
      return new Response(JSON.stringify({statuses:[{context:"octopus/verify",state:"success"}]}),{status:200});
    if (url.endsWith("/statuses/"+SHA)) {posted.push(JSON.parse(opts.body));return new Response("{}",{status:201});}
    throw Error("unexpected request");
  };
  const result=await relayOne({repository:repo,token:"ephemeral",sha:SHA,fetcher});
  assert.equal(result.outcome,"unchanged");
  assert.equal(result.state,"success");
  assert.equal(posted.length,0);
});

test("bridge 503 cannot rewrite known status", async () => {
  let count=0;
  const outcome=await relayOne({repository:repo,token:"ephemeral",sha:OTHER,fetcher:async ()=>{
    count++;return new Response("unavailable",{status:503});
  }});
  assert.equal(outcome.outcome,"bridge_unavailable");assert.equal(count,1);
});
test("status payload is exact-commit scoped and never leaks credentials", () => {
  const payload=statusPayload(SHA,"success");
  assert.equal(payload.target_url.endsWith(SHA),true);
  assert.deepEqual(Object.keys(payload).sort(),["context","description","state","target_url"].sort());
});
