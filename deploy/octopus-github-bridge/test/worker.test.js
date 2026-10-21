import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { afterEach, beforeEach, describe, it } from "node:test";

import worker, {
  missingConfig,
  pushTarget,
  reconcile,
  startVerification,
  statusForTask,
  verifySignature,
} from "../src/worker.js";

const SHA = "a".repeat(40);
const SECRET = "webhook-secret";

class MemoryKV {
  constructor() {
    this.store = new Map();
  }
  async get(key) {
    return this.store.has(key) ? this.store.get(key) : null;
  }
  async put(key, value) {
    this.store.set(key, value);
  }
  async delete(key) {
    this.store.delete(key);
  }
  async list({ prefix, limit }) {
    const keys = [...this.store.keys()].filter((key) => key.startsWith(prefix)).slice(0, limit);
    return { keys: keys.map((name) => ({ name })) };
  }
}

function makeEnv(overrides = {}) {
  return {
    GITHUB_REPOSITORY: "fuaadabdullah/AyahOS_Dual_Lineage",
    GITHUB_WEBHOOK_SECRET: SECRET,
    GITHUB_STATUS_TOKEN: "gh-token",
    OCTOPUS_URL: "https://ayahos.octopus.app/",
    OCTOPUS_API_KEY: "API-KEY",
    OCTOPUS_SPACE_ID: "Spaces-1",
    OCTOPUS_PROJECT: "AyahOS",
    OCTOPUS_ENVIRONMENT: "Verification",
    TASKS: new MemoryKV(),
    ...overrides,
  };
}

function pushPayload(overrides = {}) {
  return {
    ref: "refs/heads/fix/retire-circleci-octopus",
    after: SHA,
    deleted: false,
    repository: { full_name: "fuaadabdullah/AyahOS_Dual_Lineage" },
    ...overrides,
  };
}

function sign(body, secret = SECRET) {
  return `sha256=${createHmac("sha256", secret).update(body).digest("hex")}`;
}

// Records every outbound request and answers from a route table keyed by "METHOD path".
function mockFetch(routes) {
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    const { origin, pathname } = new URL(url);
    const method = init.method || "GET";
    calls.push({ origin, method, pathname, headers: init.headers, body: init.body ? JSON.parse(init.body) : undefined });
    const route = routes[`${method} ${pathname}`];
    if (!route) return new Response("no route", { status: 404 });
    const { status = 200, json } = typeof route === "function" ? route() : route;
    return new Response(json === undefined ? "" : JSON.stringify(json), { status });
  };
  return calls;
}

const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
});

const STATUS_PATH = `/repos/fuaadabdullah/AyahOS_Dual_Lineage/statuses/${SHA}`;
const OCTOPUS_ROUTES = {
  "POST /api/Spaces-1/releases/create/v1": { json: { ReleaseId: "Releases-9", ReleaseVersion: "0.1.9" } },
  "POST /api/Spaces-1/deployments/create/untenanted/v1": {
    json: { DeploymentServerTasks: [{ DeploymentId: "Deployments-4", ServerTaskId: "ServerTasks-77" }] },
  },
  [`POST ${STATUS_PATH}`]: { status: 201, json: {} },
};

describe("webhook signature", () => {
  it("accepts the GitHub HMAC and rejects anything else", async () => {
    const body = JSON.stringify(pushPayload());
    assert.equal(await verifySignature(SECRET, body, sign(body)), true);
    assert.equal(await verifySignature(SECRET, body, sign(body, "other")), false);
    assert.equal(await verifySignature(SECRET, `${body} `, sign(body)), false);
    assert.equal(await verifySignature(SECRET, body, null), false);
    assert.equal(await verifySignature(SECRET, body, "sha1=abc"), false);
  });
});

describe("push filtering", () => {
  const env = makeEnv();
  it("verifies branch pushes to the configured repository", () => {
    assert.deepEqual(pushTarget(env, pushPayload()), { ref: "refs/heads/fix/retire-circleci-octopus", sha: SHA });
    assert.ok(!pushTarget(env, pushPayload({ repository: { full_name: "FUAADABDULLAH/ayahos_dual_lineage" } })).skip);
  });
  it("ignores forks, tags, deletions and malformed commits", () => {
    assert.ok(pushTarget(env, pushPayload({ repository: { full_name: "someone/fork" } })).skip);
    assert.ok(pushTarget(env, pushPayload({ ref: "refs/tags/v1" })).skip);
    assert.ok(pushTarget(env, pushPayload({ deleted: true, after: "0".repeat(40) })).skip);
    assert.ok(pushTarget(env, pushPayload({ after: "0".repeat(40) })).skip);
    assert.ok(pushTarget(env, pushPayload({ after: "HEAD" })).skip);
    assert.ok(pushTarget(env, pushPayload({ ref: `refs/heads/${"x".repeat(300)}` })).skip);
  });
});

describe("task state mapping", () => {
  it("maps every Octopus task state to a GitHub status", () => {
    assert.equal(statusForTask({ State: "Success" }).state, "success");
    assert.equal(statusForTask({ State: "Failed", ErrorMessage: "step api-postgres failed" }).state, "failure");
    assert.match(statusForTask({ State: "Failed", ErrorMessage: "step api-postgres failed" }).description, /api-postgres/);
    assert.equal(statusForTask({ State: "TimedOut" }).state, "failure");
    assert.equal(statusForTask({ State: "Canceled" }).state, "error");
    for (const state of ["Queued", "Executing", "Cancelling"]) {
      assert.equal(statusForTask({ State: state }).state, "pending");
    }
    assert.match(statusForTask({ State: "Executing", HasPendingInterruptions: true }).description, /manual intervention/);
  });
  it("keeps descriptions within GitHub's 140 characters", () => {
    assert.ok(statusForTask({ State: "Failed", ErrorMessage: "x".repeat(500) }).description.length <= 140);
  });
});

describe("startVerification", () => {
  it("releases the exact commit, deploys it, records the task and posts pending", async () => {
    const env = makeEnv();
    const calls = mockFetch(OCTOPUS_ROUTES);
    const result = await startVerification(env, { ref: "refs/heads/feature", sha: SHA });

    assert.deepEqual(result, { taskId: "ServerTasks-77", releaseVersion: "0.1.9" });
    const [release, deploy, status] = calls;
    assert.equal(release.origin, "https://ayahos.octopus.app");
    assert.equal(release.headers["X-Octopus-ApiKey"], "API-KEY");
    assert.deepEqual(
      { gitRef: release.body.gitRef, gitCommit: release.body.gitCommit, projectName: release.body.projectName },
      { gitRef: "refs/heads/feature", gitCommit: SHA, projectName: "AyahOS" },
    );
    assert.equal(release.body.spaceIdOrName, "Spaces-1");
    assert.deepEqual(deploy.body.environmentNames, ["Verification"]);
    assert.equal(deploy.body.releaseVersion, "0.1.9");
    assert.equal(deploy.body.useGuidedFailure, false);
    assert.equal(status.origin, "https://api.github.com");
    assert.equal(status.pathname, STATUS_PATH);
    assert.equal(status.headers.Authorization, "Bearer gh-token");
    assert.equal(status.body.state, "pending");
    assert.equal(status.body.context, "octopus/verify");
    assert.equal(status.body.target_url, "https://ayahos.octopus.app/app#/Spaces-1/tasks/ServerTasks-77");
    assert.deepEqual(JSON.parse(await env.TASKS.get("task:ServerTasks-77")).sha, SHA);
  });

  it("posts an error status when Octopus refuses the release", async () => {
    const env = makeEnv();
    const calls = mockFetch({
      ...OCTOPUS_ROUTES,
      "POST /api/Spaces-1/releases/create/v1": { status: 400, json: { ErrorMessage: "channel rule" } },
    });
    await assert.rejects(startVerification(env, { ref: "refs/heads/feature", sha: SHA }), /returned 400/);
    const status = calls.at(-1);
    assert.equal(status.pathname, STATUS_PATH);
    assert.equal(status.body.state, "error");
    assert.equal(env.TASKS.store.size, 0);
  });
});

describe("reconcile", () => {
  let env;
  beforeEach(async () => {
    env = makeEnv();
    await env.TASKS.put("task:ServerTasks-77", JSON.stringify({ sha: SHA, ref: "refs/heads/feature", state: "pending" }));
  });

  it("reports progress once and keeps the task while it runs", async () => {
    const calls = mockFetch({
      "GET /api/Spaces-1/tasks/ServerTasks-77": { json: { State: "Executing" } },
      [`POST ${STATUS_PATH}`]: { status: 201, json: {} },
    });
    await reconcile(env);
    await reconcile(env);
    assert.equal(calls.filter((call) => call.method === "POST").length, 1);
    assert.ok(env.TASKS.store.has("task:ServerTasks-77"));
  });

  it("posts the final state and forgets the task", async () => {
    const calls = mockFetch({
      "GET /api/Spaces-1/tasks/ServerTasks-77": { json: { State: "Failed", ErrorMessage: "rag-postgres failed" } },
      [`POST ${STATUS_PATH}`]: { status: 201, json: {} },
    });
    assert.deepEqual(await reconcile(env), [{ taskId: "ServerTasks-77", state: "failure" }]);
    assert.equal(calls.at(-1).body.state, "failure");
    assert.equal(env.TASKS.store.size, 0);
  });

  it("keeps the task for the next tick when GitHub is unavailable", async () => {
    mockFetch({
      "GET /api/Spaces-1/tasks/ServerTasks-77": { json: { State: "Success" } },
      [`POST ${STATUS_PATH}`]: { status: 502, json: {} },
    });
    const [result] = await reconcile(env);
    assert.match(result.error, /502/);
    assert.ok(env.TASKS.store.has("task:ServerTasks-77"));
  });
});

describe("fetch handler", () => {
  const ctx = () => {
    const pending = [];
    return { pending, waitUntil: (promise) => pending.push(promise) };
  };

  it("rejects unsigned webhooks without calling Octopus", async () => {
    const calls = mockFetch(OCTOPUS_ROUTES);
    const body = JSON.stringify(pushPayload());
    const response = await worker.fetch(
      new Request("https://bridge.example/github", {
        method: "POST",
        body,
        headers: { "X-GitHub-Event": "push", "X-Hub-Signature-256": sign(body, "wrong") },
      }),
      makeEnv(),
      ctx(),
    );
    assert.equal(response.status, 401);
    assert.equal(calls.length, 0);
  });

  it("starts verification for a signed push", async () => {
    const calls = mockFetch(OCTOPUS_ROUTES);
    const body = JSON.stringify(pushPayload());
    const context = ctx();
    const response = await worker.fetch(
      new Request("https://bridge.example/github", {
        method: "POST",
        body,
        headers: { "X-GitHub-Event": "push", "X-Hub-Signature-256": sign(body) },
      }),
      makeEnv(),
      context,
    );
    assert.equal(response.status, 202);
    await Promise.all(context.pending);
    assert.equal(calls.length, 3);
  });

  it("reports missing configuration on /healthz without leaking values", async () => {
    const response = await worker.fetch(new Request("https://bridge.example/healthz"), makeEnv({ OCTOPUS_API_KEY: "" }), ctx());
    assert.equal(response.status, 503);
    const text = await response.text();
    assert.match(text, /OCTOPUS_API_KEY/);
    assert.doesNotMatch(text, /gh-token|webhook-secret/);
    assert.deepEqual(missingConfig(makeEnv()), []);
  });
});
