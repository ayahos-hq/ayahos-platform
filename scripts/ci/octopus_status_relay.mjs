// Minimal GitHub-native status adapter. Octopus remains the only test executor.
// Uses only the workflow's short-lived GITHUB_TOKEN, never a stored PAT.
const STATES = new Set(["pending", "success", "failure", "error"]);
const SHA = /^[0-9a-f]{40}$/;
const REPO = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const CONTEXT = "octopus/verify";
const BASE = "https://ayahos-octopus-github-bridge.fuaadabdullah.workers.dev";

export function normalizeBridgeState(body, expectedSha) {
  // The bridge endpoint is authoritative only for the *requested* exact SHA.
  // A stale cache, proxy error or mismatched record cannot certify another commit.
  if (expectedSha && body?.sha !== expectedSha) return null;
  return body && typeof body.state === "string" && STATES.has(body.state)
    ? body.state : null;
}

export function canonicalHead(pr, repository) {
  return pr?.head?.repo?.full_name?.toLowerCase() === repository.toLowerCase()
    && SHA.test(pr?.head?.sha || "");
}

export function statusPayload(sha, state) {
  if (!SHA.test(sha) || !STATES.has(state)) throw Error("invalid status target");
  const message = {
    success: "Octopus exact-SHA verification passed",
    failure: "Octopus exact-SHA verification failed",
    error: "Octopus verification infrastructure error",
    pending: "Waiting for Octopus exact-SHA verification",
  }[state];
  return {state, context: CONTEXT, description: message, target_url: `${BASE}/status/${sha}`};
}

async function github(fetcher, repository, token, method, route, body) {
  const response = await fetcher(`https://api.github.com/repos/${repository}${route}`, {
    method,
    headers: {
      accept: "application/vnd.github+json",
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
      "x-github-api-version": "2022-11-28",
      "user-agent": "AyahOS-Octopus-Status-Relay",
    },
    ...(body ? {body: JSON.stringify(body)} : {}),
  });
  if (!response.ok) throw Error(`GitHub ${method} ${route.split("?")[0]}: HTTP ${response.status}`);
  return response.json();
}

export async function relayOne({repository, token, sha, fetcher = fetch}) {
  if (!SHA.test(sha)) throw Error("invalid SHA");
  const url = `${BASE}/status/${sha}`;
  const response = await fetcher(url, {headers: {accept: "application/json"}, signal: AbortSignal.timeout(10000)});
  // A not-yet-scheduled SHA must stay pending, not be misrepresented as an error.
  const state = response.status === 404 ? "pending"
    : response.ok ? normalizeBridgeState(await response.json(), sha) : null;
  if (!state) return {sha, outcome:"bridge_unavailable"};
  const existing = await github(fetcher, repository, token, "GET",
    `/commits/${sha}/status`);
  // GitHub returns newest-first statuses. Historical matching values do not
  // prove the current verdict is already published.
  const latest = existing.statuses?.find(s => s.context === CONTEXT);
  if (latest?.state === state) {
    return {sha, outcome:"unchanged", state};
  }
  // KV records expire and can briefly lag the GitHub terminal verdict.
  // Never turn an established exact-SHA pass or failure into new pending.
  if (state === "pending" && ["success", "failure", "error"].includes(latest?.state)) {
    return {sha, outcome:"unchanged", state:latest.state};
  }
  await github(fetcher, repository, token, "POST",
    `/statuses/${sha}`, statusPayload(sha, state));
  return {sha, outcome:"updated", state};
}

export async function run({repository, token, fetcher = fetch}) {
  if (!REPO.test(repository || "") || !token) throw Error("missing relay configuration");
  const open = await github(fetcher, repository, token, "GET", "/pulls?state=open&per_page=100");
  if (!Array.isArray(open)) throw Error("unexpected GitHub PR response");
  if (open.length >= 100) throw Error("open PR list is truncated; refuse incomplete verification");
  const shas = new Set(open.filter(pr=>canonicalHead(pr, repository)).map(pr=>pr.head.sha));
  const main = await github(fetcher, repository, token, "GET", "/commits/main");
  if (SHA.test(main?.sha || "")) shas.add(main.sha);
  const outcomes = [];
  for (const sha of shas) {
    try {
      outcomes.push(await relayOne({repository, token, sha, fetcher}));
    } catch (error) {
      // One infrastructure failure must not manufacture green results.
      outcomes.push({sha, outcome:"error", reason: error?.message?.slice(0,120)});
    }
  }
  console.log(JSON.stringify({checked:outcomes.length,
    updated:outcomes.filter(x=>x.outcome==="updated").length,
    unchanged:outcomes.filter(x=>x.outcome==="unchanged").length,
    notAvailable:outcomes.filter(x=>!["updated","unchanged"].includes(x.outcome)).length}));
  if (outcomes.some(x=>x.outcome==="error")) process.exitCode = 1;
  return outcomes;
}

if (process.argv[1] && import.meta.url === new URL(`file://${process.argv[1]}`).href) {
  run({repository:process.env.GITHUB_REPOSITORY, token:process.env.GITHUB_TOKEN})
    .catch(error => {console.error(error.message);process.exitCode=1;});
}
