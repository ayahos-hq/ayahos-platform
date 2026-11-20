import test from "node:test";
import assert from "node:assert/strict";
import { isCanonicalRepository, parseBridgeState, runRelay, statusPayload } from "../../../scripts/ci/octopus_status_relay.mjs";

const SHA = "a".repeat(40);

test("builds a bounded GitHub status payload", () => {
  const payload = statusPayload("success", "x".repeat(300), "https://bridge.example/status/sha");
  assert.equal(payload.state, "success");
  assert.equal(payload.context, "octopus/verify");
  assert.equal(payload.description.length, 140);
});

test("accepts only pushes from the canonical repository", () => {
  assert.equal(isCanonicalRepository({ pull_request: { head: { repo: { full_name: "AYAHOS-HQ/AYAHOS-PLATFORM" } } } }, "ayahos-hq/ayahos-platform"), true);
  assert.equal(isCanonicalRepository({ pull_request: { head: { repo: { full_name: "someone/fork" } } } }, "ayahos-hq/ayahos-platform"), false);
});

test("parses only supported bridge states", () => {
  assert.equal(parseBridgeState({ state: "pending" }), "pending");
  assert.equal(parseBridgeState({ state: "success" }), "success");
  assert.equal(parseBridgeState({ state: "unknown" }), null);
  assert.equal(parseBridgeState({}), null);
});

test("relays pending then the final bridge state", async () => {
  const posted = [];
  let reads = 0;
  const result = await runRelay({
    token: "github-token",
    repository: "ayahos-hq/ayahos-platform",
    sha: SHA,
    statusBaseUrl: "https://bridge.example",
    now: () => 1,
    sleepFn: async () => {},
    readState: async () => (++reads === 1 ? null : "success"),
    postStatus: async ({ payload }) => posted.push(payload),
  });
  assert.equal(result, "success");
  assert.deepEqual(posted.map(({ state }) => state), ["pending", "success"]);
  assert.equal(posted[1].target_url, `https://bridge.example/status/${SHA}`);
});

test("fails closed for fork pull requests", async () => {
  const posted = [];
  const result = await runRelay({
    token: "github-token",
    repository: "ayahos-hq/ayahos-platform",
    sha: SHA,
    event: { pull_request: { head: { repo: { full_name: "someone/fork" } } } },
    postStatus: async ({ payload }) => posted.push(payload),
  });
  assert.equal(result, "error");
  assert.deepEqual(posted.map(({ state }) => state), ["error"]);
});
