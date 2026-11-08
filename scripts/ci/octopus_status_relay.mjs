import { readFile } from "node:fs/promises";

const FINAL_STATES = new Set(["success", "failure", "error"]);
const SHA = /^[0-9a-f]{40}$/;
const DEFAULT_STATUS_URL = "https://ayahos-octopus-github-bridge.fuaadabdullah.workers.dev";
const DEFAULT_TIMEOUT_MS = 25 * 60 * 1000;
const DEFAULT_POLL_MS = 20 * 1000;

export function statusPayload(state, description, targetUrl) {
  return {
    state,
    context: "octopus/verify",
    description: description.slice(0, 140),
    target_url: targetUrl,
  };
}

export function isCanonicalRepository(event, repository) {
  const headRepository = event?.pull_request?.head?.repo?.full_name;
  return !headRepository || headRepository.toLowerCase() === repository.toLowerCase();
}

export function parseBridgeState(responseBody) {
  const state = responseBody?.state;
  if (typeof state !== "string") return null;
  return FINAL_STATES.has(state) || state === "pending" ? state : null;
}

function sleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function postGitHubStatus({ token, repository, sha, payload }) {
  const response = await fetch(`https://api.github.com/repos/${repository}/statuses/${sha}`, {
    method: "POST",
    headers: {
      accept: "application/vnd.github+json",
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
      "x-github-api-version": "2022-11-28",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`GitHub status request failed with HTTP ${response.status}`);
  }
}

async function readBridgeState(statusUrl) {
  const response = await fetch(statusUrl, { headers: { accept: "application/json" } });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Octopus bridge returned HTTP ${response.status}`);
  return parseBridgeState(await response.json());
}

export async function runRelay({
  token,
  repository,
  sha,
  statusBaseUrl = DEFAULT_STATUS_URL,
  event,
  timeoutMs = DEFAULT_TIMEOUT_MS,
  pollMs = DEFAULT_POLL_MS,
  now = () => Date.now(),
  sleepFn = sleep,
  postStatus = postGitHubStatus,
  readState = readBridgeState,
}) {
  if (!token) throw new Error("GITHUB_TOKEN is required");
  if (!repository) throw new Error("GITHUB_REPOSITORY is required");
  if (!SHA.test(sha ?? "")) throw new Error("GITHUB_SHA must be a 40-character lowercase commit SHA");

  const statusUrl = `${statusBaseUrl.replace(/\/+$/, "")}/status/${sha}`;
  if (!isCanonicalRepository(event, repository)) {
    await postStatus({
      token,
      repository,
      sha,
      payload: statusPayload("error", "Fork pushes are not verified by the Octopus bridge", statusUrl),
    });
    return "error";
  }

  await postStatus({
    token,
    repository,
    sha,
    payload: statusPayload("pending", "Waiting for Octopus verification", statusUrl),
  });

  const deadline = now() + timeoutMs;
  while (now() < deadline) {
    const state = await readState(statusUrl);
    if (state && FINAL_STATES.has(state)) {
      await postStatus({
        token,
        repository,
        sha,
        payload: statusPayload(state, `Octopus verification ${state}`, statusUrl),
      });
      return state;
    }
    await sleepFn(Math.min(pollMs, Math.max(0, deadline - now())));
  }

  await postStatus({
    token,
    repository,
    sha,
    payload: statusPayload("error", "Octopus verification timed out", statusUrl),
  });
  return "error";
}

async function main() {
  const event = process.env.GITHUB_EVENT_PATH
    ? JSON.parse(await readFile(process.env.GITHUB_EVENT_PATH, "utf8"))
    : undefined;
  const result = await runRelay({
    token: process.env.GITHUB_TOKEN,
    repository: process.env.GITHUB_REPOSITORY,
    sha: process.env.GITHUB_SHA,
    statusBaseUrl: process.env.OCTOPUS_STATUS_URL,
    event,
  });
  if (result !== "success") process.exitCode = 1;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
