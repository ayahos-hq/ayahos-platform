import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { afterEach, test } from "node:test";
import worker, { reconcile, startVerification, statusForTask } from "../src/worker.js";

const SHA = "a".repeat(40);
const CORE_SHA = "b".repeat(40);
const OLD_PLATFORM_SHA = "c".repeat(40);
const API = "https://ayahos.octopus.app/api/Spaces-1";
const PROJECT_ID = "Projects-42";
const SNAPSHOT_ID = "deploymentprocess-Projects-42-s-1";
const RELEASE_ID = "Releases-42";
const RELEASE_VERSION = "1.0.42";
const TEMPLATE_PATH = `${API}/projects/${PROJECT_ID}/deploymentprocesses/template`;
const SNAPSHOT_PATH = `${API}/deploymentprocesses/${SNAPSHOT_ID}/template`;
const PROCESS_PATH = `${API}/deploymentprocesses/${SNAPSHOT_ID}`;
const RELEASE_PATH = `${API}/releases/${RELEASE_ID}`;
const MANIFEST_PATH = `https://raw.githubusercontent.com/ayahos-hq/ayahos-platform/${SHA}/release-manifest.json`;
const LANES = [...readFileSync(new URL("../../../.octopus/deployment_process.ocl", import.meta.url), "utf8")
  .matchAll(/^    name = "([^"]+)"\r?$/gm)].map((match) => match[1]).slice(0, 8);
const SIBLINGS = ["admin", "site", "workloads"];
const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

function template(full = false) {
  return {
    GitResources: [
      { ActionName: "Platform verification", RepositoryUri: "https://github.com/ayahos-hq/ayahos-platform.git" },
      { ActionName: "Cross-repo source verification", Name: "platform", RepositoryUri: "https://github.com/ayahos-hq/ayahos-platform" },
      { ActionName: "Cross-repo source verification", Name: "core", RepositoryUri: "git@github.com:ayahos-hq/ayahos-core.git" },
      ...(full ? SIBLINGS.map((name) => ({
        ActionName: "Cross-repo source verification", Name: name,
        RepositoryUri: `https://github.com/ayahos-hq/ayahos-${name}`,
      })) : []),
    ],
  };
}

function releaseFixture(full = false) {
  return {
    Id: RELEASE_ID, ProjectId: PROJECT_ID, Version: RELEASE_VERSION,
    ProjectDeploymentProcessSnapshotId: SNAPSHOT_ID,
    SelectedGitResources: [
      { ActionName: "Cross-repo source verification", GitResourceReferenceName: "core", GitReferenceResource: { GitCommit: CORE_SHA } },
      { ActionName: "Platform verification", GitReferenceResource: { GitCommit: SHA } },
      { ActionName: "Cross-repo source verification", GitResourceReferenceName: "platform", GitReferenceResource: { GitCommit: SHA } },
      ...(full ? SIBLINGS.map((name) => ({
        ActionName: "Cross-repo source verification", GitResourceReferenceName: name,
        GitReferenceResource: { GitCommit: CORE_SHA },
      })) : []),
    ],
  };
}

function releaseApi(url, options, full = false) {
  switch (url) {
    case `${API}/projects/ayahos-hq-verification`:
      assert.equal(options.method, "GET");
      return Response.json({ Id: PROJECT_ID, Name: "AyahOS HQ Verification", IsVersionControlled: false });
    case TEMPLATE_PATH:
    case SNAPSHOT_PATH:
      assert.equal(options.method, "GET");
      return Response.json(template(full));
    case MANIFEST_PATH:
      assert.equal(options.headers, undefined);
      return Response.json({
        schema_version: 1, release_status: "candidate",
        components: {
          "ayahos-core": { repository: "ayahos-hq/ayahos-core", git_sha: CORE_SHA },
          "ayahos-platform": { repository: "ayahos-hq/ayahos-platform", git_sha: OLD_PLATFORM_SHA },
          ...Object.fromEntries(SIBLINGS.map((name) => [
            `ayahos-${name}`, { repository: `ayahos-hq/ayahos-${name}`, git_sha: CORE_SHA },
          ])),
        },
      });
    case `${API}/releases/create/v1`:
      assert.equal(options.method, "POST");
      assert.deepEqual(JSON.parse(options.body), {
        spaceId: "Spaces-1", spaceIdOrName: "Spaces-1", projectName: "AyahOS HQ Verification",
        gitResources: [
          `Platform verification:${SHA}`,
          `Cross-repo source verification:platform:${SHA}`,
          `Cross-repo source verification:core:${CORE_SHA}`,
          ...(full ? SIBLINGS.map((name) => `Cross-repo source verification:${name}:${CORE_SHA}`) : []),
        ],
        ignoreIfAlreadyExists: false, ignoreChannelRules: false,
      });
      return Response.json({ ReleaseId: RELEASE_ID, ReleaseVersion: RELEASE_VERSION });
    case RELEASE_PATH:
      assert.equal(options.method, "GET");
      return Response.json(releaseFixture(full));
    default:
      throw new Error(`Unexpected test request: ${url}`);
  }
}

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
        delete: async (key) => store.delete(key),
        list: async ({ prefix, limit }) => ({
          keys: [...store.keys()].filter((key) => key.startsWith(prefix)).slice(0, limit).map((name) => ({ name })),
        }),
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
    return releaseApi(url, options);
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

test("GitHub status rejection must not falsely mark an already-created Octopus task as failed", async () => {
  const { env, store } = bridgeEnv();
  const posts = [];
  globalThis.fetch = async (url, options = {}) => {
    const path = new URL(url).pathname;
    if (path.endsWith("/deployments/create/untenanted/v1")) {
      const request = JSON.parse(options.body);
      assert.equal(request.projectName, "AyahOS HQ Verification");
      assert.equal(request.releaseVersion, RELEASE_VERSION);
      assert.deepEqual(request.environmentNames, ["Development"]);
      return Response.json({ DeploymentServerTasks: [{ ServerTaskId: "ServerTasks-42" }] });
    }
    if (String(url).startsWith("https://api.github.com/")) {
      posts.push(JSON.parse(options.body));
      return new Response("unauthorized", { status: 403 });
    }
    return releaseApi(url, options);
  };
  await assert.rejects(
    startVerification(env, { ref: "refs/heads/fixture", sha: SHA }),
    /GitHub status.*HTTP 403/,
  );
  assert.equal(posts.length, 1, "a status-post failure must not trigger a false release-start error status");
  assert.equal(posts[0].state, "pending");
  assert.deepEqual(JSON.parse(store.get(`result:${SHA}`)), { state: "pending" });
  assert.equal(JSON.parse(store.get("task:ServerTasks-42")).sha, SHA);
});

test("reconciler publishes success only after Octopus task success when GitHub status posting recovers", async () => {
  const { env, store } = bridgeEnv();
  const statusPosts = [];
  let githubAvailable = false;
  globalThis.fetch = async (url, options = {}) => {
    const path = new URL(url).pathname;
    if (path.endsWith("/deployments/create/untenanted/v1")) {
      return Response.json({ DeploymentServerTasks: [{ ServerTaskId: "ServerTasks-43" }] });
    }
    if (path.endsWith("/tasks/ServerTasks-43")) {
      return Response.json({ State: "Success" });
    }
    if (String(url).startsWith("https://api.github.com/")) {
      statusPosts.push(JSON.parse(options.body));
      return new Response("{}", { status: githubAvailable ? 201 : 403 });
    }
    return releaseApi(url, options);
  };
  await assert.rejects(startVerification(env, { ref: "refs/heads/fixture", sha: SHA }), /HTTP 403/);
  assert.equal(JSON.parse(store.get(`result:${SHA}`)).state, "pending");
  assert.ok(store.has("task:ServerTasks-43"));

  githubAvailable = true;
  assert.deepEqual(await reconcile(env), [{ taskId: "ServerTasks-43", state: "success" }]);
  assert.deepEqual(statusPosts.map((post) => post.state), ["pending", "success"]);
  assert.equal(statusPosts[1].context, "octopus/hq-operator-verified/preview");
  assert.deepEqual(JSON.parse(store.get(`result:${SHA}`)), { state: "success" });
  assert.equal(store.has("task:ServerTasks-43"), false);
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

test("a successful task queued without verified Git selections cannot certify a commit", async () => {
  const { env, store } = bridgeEnv();
  store.set("task:ServerTasks-legacy", JSON.stringify({ sha: SHA }));
  const posts = [];
  globalThis.fetch = async (url, options = {}) => {
    if (url === `${API}/tasks/ServerTasks-legacy`) return Response.json({ State: "Success" });
    assert.equal(url, `https://api.github.com/repos/ayahos-hq/ayahos-platform/statuses/${SHA}`);
    posts.push(JSON.parse(options.body));
    return Response.json({});
  };
  assert.deepEqual(await reconcile(env), [{ taskId: "ServerTasks-legacy", state: "error" }]);
  assert.equal(posts[0].state, "error");
  assert.deepEqual(JSON.parse(store.get(`result:${SHA}`)), { state: "error" });
  assert.equal(store.has("task:ServerTasks-legacy"), false);
});

for (const { name, full, disabled, skipped, state } of [
  { name: "source-only task", full: false, state: "failure" },
  { name: "disabled required lane", full: true, disabled: true, state: "failure" },
  { name: "skipped required lane", full: true, skipped: true, state: "failure" },
  { name: "five repositories and eight successful lanes", full: true, state: "success" },
]) {
  test(`canonical acceptance evaluates: ${name}`, async () => {
    assert.equal(LANES.length, 8);
    const { env, store } = bridgeEnv();
    env.STATUS_CONTEXT = "octopus/hq-operator-verified";
    const taskPath = `${API}/tasks/ServerTasks-42`;
    const stepNames = [...LANES, "Platform verification", "Cross-repo source verification"];
    const posts = [];
    globalThis.fetch = async (url, options = {}) => {
      if (url === PROCESS_PATH && full) {
        return Response.json({ Steps: stepNames.map((name, index) => ({
          Name: name, Condition: "Success",
          Actions: [{ Name: name, IsRequired: true, IsDisabled: Boolean(disabled && index === 0) }],
        })) });
      }
      if (url === `${API}/deployments/create/untenanted/v1`) {
        return Response.json({ DeploymentServerTasks: [{ ServerTaskId: "ServerTasks-42" }] });
      }
      if (url === taskPath) return Response.json({ State: "Success" });
      if (url === `${taskPath}/details` && full) {
        return Response.json({ ActivityLogs: [{ Children: stepNames.map((name, index) => ({
          Name: `Step ${index + 1}: ${name}`, Status: skipped && index === 0 ? "Skipped" : "Success",
        })) }] });
      }
      if (String(url).startsWith("https://api.github.com/")) {
        posts.push(JSON.parse(options.body));
        return Response.json({});
      }
      return releaseApi(url, options, full);
    };
    await startVerification(env, { ref: "refs/heads/fixture", sha: SHA });
    assert.deepEqual(await reconcile(env), [{ taskId: "ServerTasks-42", state }]);
    assert.deepEqual(posts.map((post) => post.state), ["pending", state]);
    assert.equal(posts[1].context, env.STATUS_CONTEXT);
    assert.deepEqual(JSON.parse(store.get(`result:${SHA}`)), { state });
  });
}

const releaseMismatchCases = [
  ["a missing Core resource", TEMPLATE_PATH, () => ({ GitResources: template().GitResources.slice(0, 2) }), /missing Platform or Core/],
  ["an invalid Core pin", MANIFEST_PATH, () => ({ schema_version: 1, release_status: "candidate", components: {} }), /valid Git resource pin/],
  ["a partial release selection", RELEASE_PATH, () => {
    const release = releaseFixture();
    release.SelectedGitResources.pop();
    return release;
  }, /expected Git resource selection/],
  ["a different selected commit", RELEASE_PATH, () => {
    const release = releaseFixture();
    release.SelectedGitResources[0].GitReferenceResource.GitCommit = OLD_PLATFORM_SHA;
    return release;
  }, /different Git repository or commit/],
  ["duplicate selected resources", RELEASE_PATH, () => {
    const release = releaseFixture();
    release.SelectedGitResources[1] = release.SelectedGitResources[2];
    return release;
  }, /different Git repository or commit/],
  ["a changed resource repository in the snapshot", SNAPSHOT_PATH, () => {
    const snapshot = template();
    snapshot.GitResources[1].RepositoryUri = "https://github.com/ayahos-hq/ayahos-core";
    return snapshot;
  }, /different Git repository or commit/],
];

for (const [name, route, responseBody, reason] of releaseMismatchCases) {
  test(`refuses to deploy when Octopus or the candidate has ${name}`, async () => {
    const { env, store } = bridgeEnv();
    const requests = [];
    globalThis.fetch = async (url, options = {}) => {
      requests.push(String(url));
      if (url === route) return Response.json(responseBody());
      if (String(url).startsWith("https://api.github.com/")) return Response.json({});
      return releaseApi(url, options);
    };
    await assert.rejects(startVerification(env, { ref: "refs/heads/fixture", sha: SHA }), reason);
    assert.equal(requests.some((url) => url.includes("/deployments/")), false);
    assert.deepEqual(JSON.parse(store.get(`result:${SHA}`)), { state: "error" });
  });
}
