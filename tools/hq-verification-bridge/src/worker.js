// Octopus <-> GitHub bridge (Cloudflare Worker).
//
// Octopus cannot create releases for pull-request branches on its own (Git triggers only follow
// the default branch) and it reports nothing to GitHub. This worker closes both gaps:
//
//   1. A signed GitHub `push` webhook creates an HQ release with exact deployment-step Git
//      revisions and queues it in Development. The commit gets a `pending` status linking the task.
//   2. A cron trigger polls each task it started and posts `success`, `failure` or `error`.
//
// The latest state per commit is also kept in KV and served read-only at GET /status/<sha>, so a
// consumer (see README.md) can read the outcome without any GitHub token in the Worker.
// GITHUB_STATUS_TOKEN is optional: when it is set the Worker also posts commit statuses itself,
// and that post never depends on the KV write succeeding.
//
// The Octopus API key and the optional GitHub token live only here, never in the Octopus process,
// so code on a branch under test cannot read them. Pushes from other repositories, tag pushes and
// branch deletions are ignored.

const GITHUB_API = "https://api.github.com";
const HQ_PLATFORM = "ayahos-hq/ayahos-platform";
const HQ_COMPONENT = /^ayahos-(?:admin|core|platform|site|workloads)$/;
const HQ_PROJECT_SLUG = "ayahos-hq-verification";
const TASK_PREFIX = "task:";
const RESULT_PREFIX = "result:";
const TASK_TTL_SECONDS = 7 * 24 * 60 * 60;
// Two subrequests per task (Octopus read + GitHub write) stay under the Workers free-plan cap.
const MAX_TASKS_PER_TICK = 20;
const SHA = /^[0-9a-f]{40}$/;
const ZERO_SHA = "0".repeat(40);
const MAX_REF_LENGTH = 255;
const DESCRIPTION_LIMIT = 140;
const READ_TIMEOUT_MS = 10_000;

const REQUIRED_ENV = [
  "GITHUB_REPOSITORY",
  "GITHUB_WEBHOOK_SECRET",
  "OCTOPUS_URL",
  "OCTOPUS_API_KEY",
  "OCTOPUS_SPACE_ID",
  "OCTOPUS_PROJECT",
  "OCTOPUS_ENVIRONMENT",
];

export function missingConfig(env) {
  const missing = REQUIRED_ENV.filter((name) => !env[name]);
  if (!env.TASKS) missing.push("TASKS (KV binding)");
  return missing;
}

function statusContext(env) {
  return env.STATUS_CONTEXT || "octopus/verify";
}

function octopusBase(env) {
  return env.OCTOPUS_URL.replace(/\/+$/, "");
}

export function taskUrl(env, taskId) {
  return `${octopusBase(env)}/app#/${env.OCTOPUS_SPACE_ID}/tasks/${encodeURIComponent(taskId)}`;
}

function truncate(text, limit = DESCRIPTION_LIMIT) {
  const clean = String(text ?? "").replace(/\s+/g, " ").trim();
  return clean.length <= limit ? clean : `${clean.slice(0, limit - 1)}…`;
}

function hex(buffer) {
  return [...new Uint8Array(buffer)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function constantTimeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export async function verifySignature(secret, body, header) {
  if (!header || !header.startsWith("sha256=")) return false;
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const mac = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body));
  return constantTimeEqual(`sha256=${hex(mac)}`, header);
}

// Returns {ref, sha} for a push this bridge should verify, or {skip: reason}.
export function pushTarget(env, payload) {
  const repository = payload?.repository?.full_name;
  if (typeof repository !== "string" || repository.toLowerCase() !== env.GITHUB_REPOSITORY.toLowerCase()) {
    return { skip: "push is not for the configured repository" };
  }
  const ref = payload.ref;
  if (typeof ref !== "string" || !ref.startsWith("refs/heads/") || ref.length > MAX_REF_LENGTH) {
    return { skip: "not a branch push" };
  }
  const sha = payload.after;
  if (payload.deleted || typeof sha !== "string" || !SHA.test(sha) || sha === ZERO_SHA) {
    return { skip: "branch deletion or missing commit" };
  }
  return { ref, sha };
}

// Octopus task state -> GitHub commit status.
export function statusForTask(task) {
  switch (task.State) {
    case "Success":
      return { state: "success", description: "All required Octopus gates passed" };
    case "Failed":
      return { state: "failure", description: "Octopus gates failed; see protected task log" };
    case "TimedOut":
      return { state: "failure", description: "Octopus task timed out" };
    case "Canceled":
      return { state: "error", description: "Octopus task was canceled" };
    default:
      if (task.HasPendingInterruptions) {
        return { state: "pending", description: "Octopus task is waiting on a manual intervention" };
      }
      return { state: "pending", description: "Octopus verification in progress" };
  }
}

async function octopus(env, method, path, body) {
  const response = await fetch(`${octopusBase(env)}${path}`, {
    method,
    redirect: "error",
    ...(method === "GET" ? { signal: AbortSignal.timeout(READ_TIMEOUT_MS) } : {}),
    headers: {
      "X-Octopus-ApiKey": env.OCTOPUS_API_KEY,
      Accept: "application/json",
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  // Octopus response bodies can contain confidential operator diagnostics.
  // Do not include them in public GitHub statuses or logged errors.
  if (!response.ok) {
    throw new Error(`Octopus ${method} ${path.split("?")[0]} returned HTTP ${response.status}`);
  }
  try {
    return await response.json();
  } catch {
    throw new Error("Octopus returned an invalid JSON response");
  }
}

function resourceKey(action, name) {
  const validName = (value) => typeof value === "string" && /^[^:\r\n*]+$/.test(value.trim());
  if (!validName(action) || (name && !validName(name))) {
    throw new Error("Octopus Git resource has an invalid action or resource name");
  }
  return name ? `${action}:${name}` : action;
}

function gitResources(template) {
  if (!Array.isArray(template.GitResources)) {
    throw new Error("Octopus release template did not list Git resources");
  }
  const resources = new Map();
  for (const resource of template.GitResources) {
    const key = resourceKey(resource.ActionName, resource.Name);
    const uri = typeof resource.RepositoryUri === "string" ? resource.RepositoryUri.toLowerCase() : "";
    const component = /^(?:https:\/\/github\.com\/|git@github\.com:|ssh:\/\/git@github\.com\/)ayahos-hq\/([a-z-]+)(?:\.git)?$/.exec(uri)?.[1];
    if (!HQ_COMPONENT.test(component ?? "") || resources.has(key)) {
      throw new Error("Octopus release template has an unknown or duplicate Git resource");
    }
    resources.set(key, component);
  }
  const components = new Set(resources.values());
  if (!components.has("ayahos-platform") || !components.has("ayahos-core")) {
    throw new Error("Octopus release template is missing Platform or Core Git resources");
  }
  return resources;
}

async function createVerifiedRelease(env, sha) {
  const spacePath = `/api/${env.OCTOPUS_SPACE_ID}`;
  if (env.GITHUB_REPOSITORY !== HQ_PLATFORM || !SHA.test(sha) || sha === ZERO_SHA
      || env.OCTOPUS_ENVIRONMENT !== "Development") {
    throw new Error("HQ release verification requires the Platform repository, full SHA and Development");
  }
  const project = await octopus(env, "GET", `${spacePath}/projects/${HQ_PROJECT_SLUG}`);
  if (!project.Id || project.Name !== env.OCTOPUS_PROJECT || project.IsVersionControlled !== false) {
    throw new Error("Octopus project does not match the database-backed HQ verification project");
  }
  const templatePath = `${spacePath}/projects/${encodeURIComponent(project.Id)}/deploymentprocesses/template`;
  const resources = gitResources(await octopus(env, "GET", templatePath));

  const response = await fetch(`https://raw.githubusercontent.com/${HQ_PLATFORM}/${sha}/release-manifest.json`, {
    redirect: "error",
    signal: AbortSignal.timeout(READ_TIMEOUT_MS),
  });
  if (!response.ok) throw new Error(`Candidate release manifest returned HTTP ${response.status}`);
  const manifest = await response.json();
  if (manifest.schema_version !== 1 || manifest.release_status !== "candidate") {
    throw new Error("Invalid candidate release manifest");
  }
  const expected = new Map();
  for (const [key, component] of resources) {
    const pin = manifest.components?.[component];
    if (pin?.repository !== `ayahos-hq/${component}` || !SHA.test(pin.git_sha ?? "") || pin.git_sha === ZERO_SHA) {
      throw new Error("Candidate release manifest is missing a valid Git resource pin");
    }
    expected.set(key, component === "ayahos-platform" ? sha : pin.git_sha);
  }

  const created = await octopus(env, "POST", `${spacePath}/releases/create/v1`, {
    spaceId: env.OCTOPUS_SPACE_ID,
    spaceIdOrName: env.OCTOPUS_SPACE_ID,
    projectName: project.Name,
    gitResources: [...expected].map(([key, commit]) => `${key}:${commit}`),
    ignoreIfAlreadyExists: false,
    ignoreChannelRules: false,
  });
  if (!created.ReleaseId || !created.ReleaseVersion) {
    throw new Error("Octopus did not return a release ID and version");
  }
  const release = await octopus(env, "GET", `${spacePath}/releases/${encodeURIComponent(created.ReleaseId)}`);
  if (release.Id !== created.ReleaseId || release.ProjectId !== project.Id || release.Version !== created.ReleaseVersion
      || !Array.isArray(release.SelectedGitResources) || release.SelectedGitResources.length !== expected.size) {
    throw new Error("Octopus release did not report the expected Git resource selection");
  }
  const snapshotId = release.ProjectDeploymentProcessSnapshotId;
  if (!snapshotId) throw new Error("Octopus release did not report a deployment process snapshot");
  const snapshot = gitResources(await octopus(env, "GET", `${spacePath}/deploymentprocesses/${encodeURIComponent(snapshotId)}/template`));
  const seen = new Set();
  for (const selected of release.SelectedGitResources) {
    const key = resourceKey(selected.ActionName, selected.GitResourceReferenceName);
    if (seen.has(key) || !expected.has(key) || resources.get(key) !== snapshot.get(key)
        || selected.GitReferenceResource?.GitCommit !== expected.get(key)) {
      throw new Error("Octopus release selected a different Git repository or commit");
    }
    seen.add(key);
  }
  if (snapshot.size !== expected.size) {
    throw new Error("Octopus release snapshot has unexpected Git resources");
  }
  return release;
}

export async function postStatus(env, sha, { state, description, targetUrl }) {
  const response = await fetch(`${GITHUB_API}/repos/${env.GITHUB_REPOSITORY}/statuses/${sha}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_STATUS_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "ayahos-octopus-github-bridge",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      state,
      description: truncate(description),
      context: statusContext(env),
      ...(targetUrl ? { target_url: targetUrl } : {}),
    }),
  });
  if (!response.ok) {
    throw new Error(`GitHub status for ${sha} returned HTTP ${response.status}`);
  }
}

// Keep the latest state per commit for GET /status/<sha>, and post it to GitHub when a token is set.
// With a token the GitHub post is authoritative: a KV failure is logged but never blocks it, and a
// post failure still propagates so reconcile keeps the task for the next tick. Without a token the
// KV record is the only channel, so its failure propagates instead.
async function reportStatus(env, sha, status) {
  let recordError = null;
  try {
    await env.TASKS.put(`${RESULT_PREFIX}${sha}`, JSON.stringify({ state: status.state }), {
      expirationTtl: TASK_TTL_SECONDS,
    });
  } catch (error) {
    recordError = error;
  }
  if (env.GITHUB_STATUS_TOKEN) {
    if (recordError) console.error(`result ${sha}: ${recordError.message}`);
    await postStatus(env, sha, status);
  } else if (recordError) {
    throw recordError;
  }
}

// Create the release on the pushed commit, deploy it to the verification environment, and
// record the task so the cron trigger can report its outcome.
export async function startVerification(env, { ref, sha }) {
  const space = env.OCTOPUS_SPACE_ID;
  let taskId;
  let releaseVersion;
  try {
    const release = await createVerifiedRelease(env, sha);
    const deployment = await octopus(env, "POST", `/api/${space}/deployments/create/untenanted/v1`, {
      spaceId: space,
      spaceIdOrName: space,
      projectName: env.OCTOPUS_PROJECT,
      releaseVersion: release.Version,
      environmentNames: [env.OCTOPUS_ENVIRONMENT],
      forcePackageDownload: false,
      forcePackageRedeployment: false,
      updateVariableSnapshot: false,
      // A failed gate must fail the task, not park it waiting for someone to click retry.
      useGuidedFailure: false,
    });
    taskId = deployment.DeploymentServerTasks?.[0]?.ServerTaskId;
    if (!taskId || deployment.DeploymentServerTasks.length !== 1) {
      throw new Error("Octopus deployment response did not identify exactly one server task");
    }
    releaseVersion = release.Version;
    await env.TASKS.put(
      `${TASK_PREFIX}${taskId}`,
      JSON.stringify({ sha, ref, releaseVersion, gitSelectionVerified: true }),
      { expirationTtl: TASK_TTL_SECONDS },
    );
  } catch (error) {
    // Only an actual Octopus release/deployment or task-recording failure means
    // verification could not start. GitHub posting is handled separately.
    await reportStatus(env, sha, {
      state: "error",
      description: "Could not start Octopus verification; inspect protected operator logs",
    }).catch(() => {});
    throw error;
  }

  // The Octopus task already exists. A missing/expired GitHub status token must
  // not overwrite it with a false "could not start" error. The task remains in
  // KV and the scheduled reconciler can retry reporting on the next tick.
  await reportStatus(env, sha, {
    state: "pending",
    description: "Octopus verification queued",
    targetUrl: taskUrl(env, taskId),
  });
  return { taskId, releaseVersion };
}

// One cron tick: report every recorded task whose state changed; forget finished ones.
export async function reconcile(env) {
  const listing = await env.TASKS.list({ prefix: TASK_PREFIX, limit: MAX_TASKS_PER_TICK });
  const results = [];
  for (const { name } of listing.keys) {
    const taskId = name.slice(TASK_PREFIX.length);
    try {
      const record = JSON.parse((await env.TASKS.get(name)) ?? "null");
      if (!record) continue;
      const task = await octopus(env, "GET", `/api/${env.OCTOPUS_SPACE_ID}/tasks/${encodeURIComponent(taskId)}`);
      const status = task.State === "Success" && record.gitSelectionVerified !== true
        ? { state: "error", description: "Octopus task has no verified Git resource selection; rerun verification" }
        : statusForTask(task);
      const key = `${status.state}:${status.description}`;
      if (key !== record.reported) {
        await reportStatus(env, record.sha, { ...status, targetUrl: taskUrl(env, taskId) });
      }
      if (status.state === "pending") {
        if (key !== record.reported) {
          await env.TASKS.put(name, JSON.stringify({ ...record, reported: key }), { expirationTtl: TASK_TTL_SECONDS });
        }
      } else {
        await env.TASKS.delete(name);
      }
      results.push({ taskId, state: status.state });
    } catch (error) {
      // Leave the record for the next tick; one bad task must not block the others.
      console.error(`reconcile ${taskId}: ${error.message}`);
      results.push({ taskId, error: error.message });
    }
  }
  return results;
}

async function handleWebhook(request, env, ctx) {
  const body = await request.text();
  if (!(await verifySignature(env.GITHUB_WEBHOOK_SECRET, body, request.headers.get("X-Hub-Signature-256")))) {
    return new Response("invalid signature\n", { status: 401 });
  }
  const event = request.headers.get("X-GitHub-Event");
  if (event === "ping") return new Response("pong\n");
  if (event !== "push") return new Response(`ignored event ${event}\n`, { status: 202 });

  let payload;
  try {
    payload = JSON.parse(body);
  } catch {
    return new Response("invalid JSON\n", { status: 400 });
  }
  const target = pushTarget(env, payload);
  if (target.skip) return new Response(`ignored: ${target.skip}\n`, { status: 202 });

  // GitHub gives a webhook ten seconds; release creation can take longer, so finish after replying.
  ctx.waitUntil(
    startVerification(env, target).catch((error) => console.error(`start ${target.sha}: ${error.message}`)),
  );
  return new Response(`verifying ${target.sha}\n`, { status: 202 });
}

const RESULT_STATES = new Set(["pending", "success", "failure", "error"]);
const NO_STORE = { "Cache-Control": "no-store" };

// Only the state is exposed: Octopus error text and task links stay out of this unauthenticated route.
// A missing, unparsable or unrecognised record is "unknown", never a guess.
async function handleStatus(env, sha) {
  if (!SHA.test(sha)) return new Response("invalid commit\n", { status: 400, headers: NO_STORE });
  let record = null;
  try {
    record = JSON.parse((await env.TASKS.get(`${RESULT_PREFIX}${sha}`)) ?? "null");
  } catch {
    record = null;
  }
  if (!record || !RESULT_STATES.has(record.state)) {
    return new Response("unknown commit\n", { status: 404, headers: NO_STORE });
  }
  return Response.json({ sha, state: record.state }, { headers: NO_STORE });
}

export default {
  async fetch(request, env, ctx) {
    const { pathname } = new URL(request.url);
    const missing = missingConfig(env);
    const statusMatch = pathname.match(/^\/status\/([^/]+)$/);
    if (statusMatch && request.method === "GET") {
      if (missing.length) return new Response("bridge is not configured\n", { status: 503 });
      return handleStatus(env, statusMatch[1]);
    }
    if (pathname === "/healthz") {
      return missing.length
        ? new Response(`missing configuration: ${missing.join(", ")}\n`, { status: 503 })
        : new Response("ok\n");
    }
    if (pathname === "/github" && request.method === "POST") {
      if (missing.length) return new Response("bridge is not configured\n", { status: 503 });
      return handleWebhook(request, env, ctx);
    }
    return new Response("not found\n", { status: 404 });
  },

  async scheduled(_controller, env, ctx) {
    if (missingConfig(env).length) return;
    ctx.waitUntil(reconcile(env));
  },
};
