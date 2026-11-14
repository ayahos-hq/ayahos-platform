import { test } from "node:test";
import assert from "node:assert/strict";
import { missingConfig, assessNode, buildReport } from "../src/worker.js";

const NOW = 1761000000;

function node(overrides = {}) {
  return {
    node_id: "node-001",
    status: "online",
    backend: "llama.cpp",
    gpu: "RTX 3060 12GB",
    models: [{ id: "qwen3-8b", brain_role: "cognitive" }],
    brain_roles: ["cognitive"],
    active_jobs: 0,
    max_concurrency: 2,
    consecutive_failures: 0,
    last_heartbeat: NOW,
    ...overrides,
  };
}

test("missingConfig reports absent keys", () => {
  assert.deepEqual(missingConfig({}), ["CORE_API_KEY"]);
  assert.deepEqual(missingConfig({ CORE_API_KEY: "x" }), []);
});

test("assessNode: fresh online node is healthy", () => {
  const a = assessNode(node(), NOW);
  assert.equal(a.healthy, true);
  assert.equal(a.stale, false);
  assert.equal(a.age_seconds, 0);
});

test("assessNode: stale node is unhealthy", () => {
  const a = assessNode(node({ last_heartbeat: NOW - 400 }), NOW);
  assert.equal(a.stale, true);
  assert.equal(a.healthy, false);
});

test("assessNode: offline node is unhealthy", () => {
  const a = assessNode(node({ status: "offline" }), NOW);
  assert.equal(a.healthy, false);
});

test("assessNode: 3+ consecutive failures is unhealthy", () => {
  const a = assessNode(node({ consecutive_failures: 3 }), NOW);
  assert.equal(a.healthy, false);
});

test("assessNode: 2 consecutive failures is still healthy", () => {
  const a = assessNode(node({ consecutive_failures: 2 }), NOW);
  assert.equal(a.healthy, true);
});

test("buildReport: counts healthy and degraded", () => {
  const report = buildReport([node(), node({ node_id: "node-002", status: "offline" })], NOW);
  assert.equal(report.total_nodes, 2);
  assert.equal(report.healthy_nodes, 1);
  assert.equal(report.degraded_nodes, 1);
  assert.equal(report.degraded[0].node_id, "node-002");
});

test("buildReport: brain role coverage", () => {
  const report = buildReport([
    node(),
    node({ node_id: "node-002", brain_roles: ["cognitive", "undermind"], models: [{ id: "qwen3-8b", brain_role: "cognitive" }, { id: "qwen3-4b", brain_role: "undermind" }] }),
  ], NOW);
  assert.equal(report.brain_role_coverage.cognitive.total, 2);
  assert.equal(report.brain_role_coverage.cognitive.healthy, 2);
  assert.equal(report.brain_role_coverage.undermind.total, 1);
  assert.equal(report.brain_role_coverage.undermind.healthy, 1);
});

test("buildReport: stale nodes are counted", () => {
  const report = buildReport([node({ last_heartbeat: NOW - 400 })], NOW);
  assert.equal(report.stale_nodes, 1);
});