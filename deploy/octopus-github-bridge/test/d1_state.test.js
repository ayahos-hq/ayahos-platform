import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { beforeEach, describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import worker, { reconcile } from "../src/worker.js";
import { D1BridgeState, stateStoreEnv } from "../src/d1_state.js";

function database() {
  const sql = readFileSync(new URL("../d1-schema.sql", import.meta.url), "utf8");
  const sqlite = new DatabaseSync(":memory:");
  sqlite.exec(sql);
  return {
    sqlite,
    prepare(query) {
      const stmt = sqlite.prepare(query);
      return {
        bind(...args) {
          return {
            first: async () => stmt.get(...args) ?? null,
            all: async () => ({ success: true, results: stmt.all(...args) }),
            run: async () => ({ success: true, meta: stmt.run(...args) }),
          };
        },
      };
    },
  };
}

const NOW = 1_798_000_000_000;
const SHA = "b".repeat(40);

describe("D1 bridge state replaces KV quotas without changing the wire contract", () => {
  let d1;
  let state;
  let time;
  beforeEach(() => {
    d1 = database();
    time = NOW;
    state = new D1BridgeState(d1, { now: () => time });
  });

  it("upserts values, keeps exact payload bytes and never leaks model data", async () => {
    assert.equal(await state.get("task:1"), null);
    await state.put("task:1", '{"sha":"x","ref":"refs/heads/main"}', { expirationTtl: 3600 });
    assert.equal(await state.get("task:1"), '{"sha":"x","ref":"refs/heads/main"}');
    await state.put("task:1", '{"sha":"y"}', { expirationTtl: 3600 });
    assert.equal(await state.get("task:1"), '{"sha":"y"}');
    const count = d1.sqlite.prepare("SELECT count(*) AS n FROM bridge_state").get().n;
    assert.equal(count, 1);
  });

  it("honors expiry and prunes expired state in bounded batches", async () => {
    await state.put("task:1", "1", { expirationTtl: 120 });
    await state.put("task:2", "2", { expirationTtl: 120 });
    time += 121000;
    assert.equal(await state.get("task:1"), null);
    assert.deepEqual((await state.list({ prefix: "task:" })).keys, []);
    await state.pruneExpired(1);
    assert.equal(d1.sqlite.prepare("SELECT count(*) AS n FROM bridge_state").get().n, 1);
    await state.pruneExpired(1);
    assert.equal(d1.sqlite.prepare("SELECT count(*) AS n FROM bridge_state").get().n, 0);
  });

  it("paginates stably over exact prefixes with opaque-looking cursor keys", async () => {
    for (const key of ["task:4", "task:2", "task:3", "task:1", "result:x", "attempted:y"]) {
      await state.put(key, "v", { expirationTtl: 3600 });
    }
    const one = await state.list({ prefix: "task:", limit: 2 });
    assert.deepEqual(one.keys, [{ name: "task:1" }, { name: "task:2" }]);
    assert.equal(one.list_complete, false);
    const two = await state.list({ prefix: "task:", limit: 2, cursor: one.cursor });
    assert.deepEqual(two.keys, [{ name: "task:3" }, { name: "task:4" }]);
    assert.equal(two.list_complete, true);
    assert.equal(two.cursor, undefined);
    assert.deepEqual((await state.list({ prefix: "desired:" })).keys, []);
  });

  it("deletes state idempotently and rejects bad TTL/limit", async () => {
    await state.delete("missing");
    await state.put("result:x", "v");
    await state.delete("result:x");
    assert.equal(await state.get("result:x"), null);
    await assert.rejects(state.put("x", "v", { expirationTtl: -1 }), RangeError);
    await assert.rejects(state.list({ prefix: "task:", limit: 0 }), RangeError);
    await assert.rejects(state.pruneExpired(0), RangeError);
  });

  it("keeps KV mode unless explicitly promoted, even when D1 is already bound", async () => {
    const oldKV = { get: async () => "legacy" };
    assert.equal(stateStoreEnv({ STATE_DB: d1, TASKS: oldKV }).TASKS, oldKV);
    const migrated = stateStoreEnv({ STATE_BACKEND: "d1", STATE_DB: d1, TASKS: oldKV });
    assert.notEqual(migrated.TASKS, oldKV);
    await migrated.TASKS.put("result:x", '{"state":"success"}');
    assert.equal(await migrated.TASKS.get("result:x"), '{"state":"success"}');
    assert.equal(stateStoreEnv({ STATE_BACKEND: "d1", TASKS: oldKV }).TASKS, undefined);
  });

  it("returns authentic migrated D1 status, never invents success", async () => {
    await state.put("result:" + SHA, '{"state":"success"}');
    const env = {
      GITHUB_REPOSITORY: "fuaadabdullah/AyahOS_Dual_Lineage",
      GITHUB_WEBHOOK_SECRET: "secret", OCTOPUS_URL: "https://ayahos.octopus.app",
      OCTOPUS_API_KEY: "synthetic", OCTOPUS_SPACE_ID: "Spaces-1",
      OCTOPUS_PROJECT: "AyahOS", OCTOPUS_ENVIRONMENT: "Development",
      STATE_DB: d1, STATE_BACKEND: "d1",
    };
    const ok = await worker.fetch(new Request("https://bridge.test/status/" + SHA), env, {});
    assert.equal(ok.status, 200);
    assert.deepEqual(await ok.json(), { sha: SHA, state: "success" });
    const unknown = await worker.fetch(new Request("https://bridge.test/status/" + "a".repeat(40)), env, {});
    assert.equal(unknown.status, 404);
  });
});


describe("D1 integration with the real bridge state transition", () => {
  it("reports terminal Octopus verification exactly once and deletes D1 task", async () => {
    const d1 = database();
    const state = new D1BridgeState(d1);
    await state.put("task:ServerTasks-5", JSON.stringify({
      sha: SHA, ref: "refs/heads/feature", reported: "pending:Octopus task queued",
    }));
    const env = stateStoreEnv({
      STATE_BACKEND: "d1", STATE_DB: d1,
      GITHUB_REPOSITORY: "fuaadabdullah/AyahOS_Dual_Lineage",
      OCTOPUS_URL: "https://ayahos.octopus.app", OCTOPUS_API_KEY: "test-key",
      OCTOPUS_SPACE_ID: "Spaces-1", OCTOPUS_PROJECT: "AyahOS",
      OCTOPUS_ENVIRONMENT: "Development", GITHUB_STATUS_TOKEN: "test-token",
    });
    const oldFetch = globalThis.fetch;
    const calls = [];
    globalThis.fetch = async (url, init) => {
      const pathname = new URL(url).pathname;
      calls.push({ pathname, method: init.method });
      if (pathname === "/api/Spaces-1/tasks/ServerTasks-5") {
        return new Response(JSON.stringify({ State: "Success" }), { status: 200 });
      }
      if (pathname.endsWith("/statuses/" + SHA)) {
        return new Response("{}", { status: 201 });
      }
      return new Response("not found", { status: 404 });
    };
    try {
      const results = await reconcile(env);
      assert.deepEqual(results, [{ taskId: "ServerTasks-5", state: "success" }]);
      assert.equal(await env.TASKS.get("task:ServerTasks-5"), null);
      assert.equal(await env.TASKS.get("result:" + SHA), '{"state":"success"}');
      assert.equal(calls.filter(x => x.pathname.endsWith("/statuses/" + SHA)).length, 1);
      assert.deepEqual(await reconcile(env), []);
    } finally {
      globalThis.fetch = oldFetch;
    }
  });
});

describe("D1 free-query budget and recovery regressions", () => {
  const runtimeEnv = (databaseBinding, extra = {}) => ({
    STATE_BACKEND: "d1", STATE_DB: databaseBinding,
    GITHUB_REPOSITORY: "fuaadabdullah/AyahOS_Dual_Lineage",
    GITHUB_WEBHOOK_SECRET: "synthetic-signing-key",
    OCTOPUS_URL: "https://ayahos.octopus.app",
    OCTOPUS_API_KEY: "synthetic-octopus-key",
    OCTOPUS_SPACE_ID: "Spaces-1", OCTOPUS_PROJECT: "AyahOS",
    OCTOPUS_ENVIRONMENT: "Development",
    ...extra,
  });

  it("processes a bounded D1 backlog without crossing 50 queries per invocation", async () => {
    const d1 = database();
    const seed = new D1BridgeState(d1);
    for (let i = 0; i < 21; i += 1) {
      await seed.put("task:ServerTasks-" + i, JSON.stringify({
        sha: i.toString(16).padStart(40, "0"),
        ref: "refs/heads/p0-test",
      }));
    }
    const originalPrepare = d1.prepare.bind(d1);
    let queries = 0;
    d1.prepare = (sql) => {
      queries += 1;
      if (queries > 50) throw new Error("D1 free per-invocation query limit");
      return originalPrepare(sql);
    };
    const env = stateStoreEnv(runtimeEnv(d1));
    const priorFetch = globalThis.fetch;
    globalThis.fetch = async () =>
      new Response(JSON.stringify({ State: "Success" }), { status: 200 });
    try {
      const processed = await reconcile(env);
      assert.equal(processed.length, 10);
      assert.ok(processed.every(item => item.state === "success"));
      assert.ok(queries <= 50);
      assert.equal(d1.sqlite.prepare === undefined, false);
    } finally {
      globalThis.fetch = priorFetch;
    }
  });

  it("prunes expired D1 rows during scheduled execution, not only from tests", async () => {
    const d1 = database();
    const state = new D1BridgeState(d1);
    for (let i = 0; i < 3; i += 1) await state.put("result:expired-" + i, "x");
    d1.sqlite.exec("UPDATE bridge_state SET expires_at = 1");
    const promises = [];
    worker.scheduled({}, runtimeEnv(d1), { waitUntil(promise) { promises.push(promise); } });
    await Promise.all(promises);
    assert.equal(d1.sqlite.prepare("SELECT count(*) AS n FROM bridge_state").get().n, 0);
  });

  it("retries failed terminal cleanup without posting duplicate GitHub status", async () => {
    const d1 = database();
    const env = stateStoreEnv(runtimeEnv(d1, { GITHUB_STATUS_TOKEN: "test-token" }));
    await env.TASKS.put("task:ServerTasks-77", JSON.stringify({
      sha: SHA, ref: "refs/heads/main",
    }));
    const realDelete = env.TASKS.delete.bind(env.TASKS);
    let failedOnce = false;
    env.TASKS.delete = async name => {
      if (name.startsWith("task:") && !failedOnce) {
        failedOnce = true;
        throw new Error("transient D1 deletion failure");
      }
      return realDelete(name);
    };
    const priorFetch = globalThis.fetch;
    let statusPosts = 0;
    globalThis.fetch = async (url) => {
      const path = new URL(url).pathname;
      if (path.endsWith("/statuses/" + SHA)) {
        statusPosts += 1;
        return new Response("{}", { status: 201 });
      }
      return new Response(JSON.stringify({ State: "Success" }), { status: 200 });
    };
    const priorConsole = console.error;
    console.error = () => {};
    try {
      const first = await reconcile(env);
      assert.equal(first[0].error, "transient D1 deletion failure");
      const second = await reconcile(env);
      assert.equal(second[0].state, "success");
      assert.equal(statusPosts, 1);
      assert.equal(await env.TASKS.get("task:ServerTasks-77"), null);
    } finally {
      console.error = priorConsole;
      globalThis.fetch = priorFetch;
    }
  });
});
