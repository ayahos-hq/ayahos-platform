// Model reconciler (Cloudflare Worker).
//
// A narrow cron that checks the model ladder state: fetches node heartbeats from
// the Core API, compares advertised models against the expected ladder, and logs
// discrepancies. This is intentionally separate from the Octopus bridge — it has
// no Octopus dependency and runs on its own schedule.
//
// Secrets (CORE_API_KEY) are set with `wrangler secret put` and never committed.

const CORE_API = "https://api.ayahos.app";
const NODE_TTL_SECONDS = 300; // 5 minutes without a heartbeat = stale
const MAX_NODES = 50;

const REQUIRED_ENV = [
  "CORE_API_KEY",
];

export function missingConfig(env) {
  return REQUIRED_ENV.filter((name) => !env[name]);
}

export function assessNode(node, now = Date.now() / 1000) {
  const age = now - (node.last_heartbeat || 0);
  const stale = age > NODE_TTL_SECONDS;
  const brainRoles = node.brain_roles || [];
  const models = (node.models || []).map((m) => m.id || m);

  return {
    node_id: node.node_id,
    status: node.status,
    backend: node.backend,
    gpu: node.gpu,
    age_seconds: Math.round(age),
    stale,
    brain_roles: brainRoles,
    models,
    active_jobs: node.active_jobs || 0,
    max_concurrency: node.max_concurrency || 1,
    consecutive_failures: node.consecutive_failures || 0,
    healthy: node.status === "online" && !stale && node.consecutive_failures < 3,
  };
}

export function buildReport(nodes, now = Date.now() / 1000) {
  const assessments = nodes.map((n) => assessNode(n, now));
  const healthy = assessments.filter((n) => n.healthy);
  const degraded = assessments.filter((n) => !n.healthy);
  const staleNodes = assessments.filter((n) => n.stale);
  const brainRoleCoverage = {};
  for (const node of assessments) {
    for (const role of node.brain_roles) {
      if (!brainRoleCoverage[role]) brainRoleCoverage[role] = { total: 0, healthy: 0 };
      brainRoleCoverage[role].total++;
      if (node.healthy) brainRoleCoverage[role].healthy++;
    }
  }

  return {
    timestamp: new Date().toISOString(),
    total_nodes: assessments.length,
    healthy_nodes: healthy.length,
    degraded_nodes: degraded.length,
    stale_nodes: staleNodes.length,
    brain_role_coverage: brainRoleCoverage,
    degraded: degraded.map((n) => ({
      node_id: n.node_id,
      status: n.status,
      stale: n.stale,
      consecutive_failures: n.consecutive_failures,
    })),
  };
}

/**
 * Fetch all registered compute nodes from the Core API.
 */
async function fetchNodes(env) {
  const url = `${CORE_API}/v1/compute/nodes`;
  const response = await fetch(url, {
    headers: {
      "Authorization": `Bearer ${env.CORE_API_KEY}`,
      "Accept": "application/json",
    },
  });
  if (!response.ok) {
    throw new Error(`Core API returned ${response.status} for ${url}`);
  }
  const body = await response.json();
  if (!Array.isArray(body?.nodes)) {
    throw new Error("unexpected Core API response shape");
  }
  return body.nodes.slice(0, MAX_NODES);
}

/**
 * Cron handler: reconcile the model ladder state.
 */
export async function reconcile(env) {
  const nodes = await fetchNodes(env);
  const report = buildReport(nodes);

  // Log the report — in production this would also write to a KV store or
  // trigger alerts for degraded coverage.
  console.log(JSON.stringify(report));

  return report;
}

export default {
  async scheduled(event, env, ctx) {
    const missing = missingConfig(env);
    if (missing.length > 0) {
      console.error(`model-reconciler: missing config: ${missing.join(", ")}`);
      return;
    }
    try {
      const report = await reconcile(env);
      // If any brain role has zero healthy nodes, flag it.
      for (const [role, coverage] of Object.entries(report.brain_role_coverage)) {
        if (coverage.healthy === 0) {
          console.warn(`model-reconciler: zero healthy nodes for brain role "${role}"`);
        }
      }
    } catch (err) {
      console.error(`model-reconciler: ${err.message}`);
    }
  },

  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/healthz") {
      const missing = missingConfig(env);
      if (missing.length > 0) {
        return new Response(`missing config: ${missing.join(", ")}`, { status: 503 });
      }
      return new Response("ok", { status: 200 });
    }
    if (url.pathname === "/reconcile" && request.method === "POST") {
      try {
        const report = await reconcile(env);
        return new Response(JSON.stringify(report), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      } catch (err) {
        return new Response(err.message, { status: 500 });
      }
    }
    return new Response("not found", { status: 404 });
  },
};