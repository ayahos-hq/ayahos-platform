# Physical Node 001 GPU proof

This runbook is the live verification gate for Milestone 3. Repository code and unit
tests are not sufficient evidence of an RTX 3060-backed request.

## Preconditions

Run the verifier from an operator machine that can reach the private control plane,
runtime API, and the node agent:

- Node 001 runs the node agent beside llama.cpp or llama-swap.
- The node agent advertises a Qwen-family cognitive model, for example
  `Qwen2.5-3B-Instruct-Q4_K_M`, with `brain_role=cognitive`.
- If a separate lightweight critic is served by the node, advertise it with
  `brain_role=autonomic` and pass `--autonomic-model`.
- The node endpoint is HTTPS unless it is loopback-only.
- `DUAL_LINEAGE_NODE_OPERATOR_SECRET` is the control-plane fleet credential.
- Optional DUAL_LINEAGE_NODE001_REGISTRATION_SECRET authenticates only node-001 heartbeats; the shared registration credential remains active for other nodes.
- `DUAL_LINEAGE_RUNTIME_API_KEY` is the authenticated cognition credential.
- `--commit-sha` is the exact deployed API/runtime commit being proven.

The node agent defaults to loopback binding. Do not expose port 8110 directly to the
public internet. If the node is reachable over a private network, use TLS and a
private allowlist; the inference secret is still mandatory.

## Run

From the repository root:

```bash
export DUAL_LINEAGE_NODE_OPERATOR_SECRET='(secret from the runtime environment)'
export DUAL_LINEAGE_RUNTIME_API_KEY='(secret from the runtime environment)'

ruby scripts/verify_node001_gpu_proof.rb \
  --control-plane https://internal-api.example \
  --runtime https://internal-api.example \
  --node-endpoint https://node-001.tailnet:8110 \
  --node-id node-001 \
  --cognitive-model Qwen2.5-3B-Instruct-Q4_K_M \
  --autonomic-model Qwen2.5-0.5B-Instruct-Q4_K_M \
  --commit-sha "$DEPLOYED_COMMIT_SHA" \
  --artifact "artifacts/node-001/proof-$DEPLOYED_COMMIT_SHA.json" \
  --offline-command 'ssh node-001 sudo systemctl stop goblin-node-agent' \
  --restore-command 'ssh node-001 sudo systemctl start goblin-node-agent' \
  --fallback-provider overmind-local
```

Use the actual control-plane base path used by the deployment. The verifier appends
`/compute/nodes/<node-id>` and `/v1/cognition`; do not append those paths twice.

## Evidence required

A successful artifact records:

- exact commit SHA and UTC timestamps;
- node ID, advertised RTX 3060 GPU, llama.cpp-compatible backend, and model roles;
- authenticated registration state;
- rejection of direct unauthenticated `/inference`;
- request ID, node ID, model, terminal result, usage, and measured latency;
- the terminal cognition trace;
- a controlled node-offline request proving the response did not use Node 001;
- restoration of the node process.

The artifact is retained evidence, not a claim that can be inferred from configuration.
Do not commit secrets or raw credentials to the artifact.

## Failure interpretation

- A missing/stale heartbeat fails registration and GPU proof.
- A node request without the inference bearer must return 401, 403, or 503.
- A cognition response without `node_id=node-001` fails routed cognition proof.
- Missing usage fails the evidence gate; do not substitute an estimated token count.
- An offline request that still reports Node 001 fails the fallback gate.
- If the offline hook is omitted, the script exits non-zero and marks the offline
  check as not run.

After a successful physical run, attach the JSON artifact to the change/operations
record and update `docs/PROJECT_STATE.md` and `docs/ROADMAP.md` with the exact
commit, timestamp, environment, and artifact path. Until then, Milestone 3 remains
unverified.
