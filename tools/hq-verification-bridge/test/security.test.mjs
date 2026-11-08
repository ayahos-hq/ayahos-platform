import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import worker, { startVerification, statusForTask } from "../src/worker.js";

const SHA = "a".repeat(40);
const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

function bridgeEnv() {
  const store = new Map();
  return {
    env: {
      GITHUB_REPOSITORY: "ayahos-hq/ayahos-platform",
      GITHUB_WEBHOOK_SECRET: "fixture-secret",
      GITHUB_STATUS_TOKEN: "fixture-github-token",
      OCTOPUS_URL: "https://ayahos.octopus.app",
      OCTOPUS_API_KEY: "fixture-octopus-key",
      OCTOPUS_SPACE_ID: "Spaces-1",
      OCTOPUS_PROJECT: "AyahOS HQ Verification",
      OCTOPUS_ENVIRONMENT: "Development",
      STATUS_CONTEXT: "octopus/hq-operator-verified/preview",
      TASKS: {
        get: async (key) => store.get(key) ?? null,
        put: async (key, value) => store.set(key, value),
      },
    },
    store,
  };
}

test("failed Octopus task messages cannot escape into GitHub status descriptions", () => {
  const result = statusForTask({
    State: "Failed",
    ErrorMessage: "credentials token=example_sensitive_secret_123",
  });
  assert.equal(result.state, "failure");
  assert.doesNotMatch(JSON.stringify(result), /example_sensitive_secret_123|credentials token=/);
});

test("a rejected Octopus release does not forward API response contents to GitHub status", async () => {
  const { env, store } = bridgeEnv();
  const posts = [];
  globalThis.fetch = async (url, options = {}) => {
    if (String(url).includes("/releases/create/v1")) {
      return new Response(JSON.stringify({
        ErrorMessage: "sensitive_password_value_456",
      }), { status: 403 });
    }
    if (String(url).startsWith("https://api.github.com/")) {
      posts.push(JSON.parse(options.body));
      return new Response("{}", { status: 201 });
    }
    throw new Error("Unexpected external request");
  };
  await assert.rejects(
    startVerification(env, { ref: "refs/heads/fixture", sha: SHA }),
    /403/,
  );
  assert.equal(posts.length, 1);
  assert.equal(posts[0].state, "error");
  assert.equal(posts[0].context, "octopus/hq-operator-verified/preview");
  assert.doesNotMatch(JSON.stringify(posts[0]), /sensitive_password|ErrorMessage/);
  assert.deepEqual(JSON.parse(store.get(`result:${SHA}`)), { state: "error" });
});

test("public status route returns only state, never recorded diagnostic fields", async () => {
  const { env, store } = bridgeEnv();
  store.set(`result:${SHA}`, JSON.stringify({ state: "failure", description: "private secret" }));
  const response = await worker.fetch(
    new Request(`https://bridge.example/status/${SHA}`), env, {},
  );
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { sha: SHA, state: "failure" });
});
