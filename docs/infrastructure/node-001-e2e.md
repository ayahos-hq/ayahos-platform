# Node 001 physical E2E evidence

`scripts/verify_node001_e2e.py` collects the bounded evidence for a physical
Node 001 proof. It is read-only with respect to both the node and the control
plane: it checks health, performs one authenticated cognitive inference, and
optionally confirms that the control plane can see the node. It never records a
credential, request prompt, model completion, endpoint, or provider response.

Run it only from an approved operator environment with managed secrets:

```sh
python3 scripts/verify_node001_e2e.py \
  --node-url "$DUAL_LINEAGE_NODE_PUBLIC_ENDPOINT" \
  --inference-secret "$DUAL_LINEAGE_NODE_INFERENCE_SECRET" \
  --model "$DUAL_LINEAGE_NODE_COGNITIVE_MODEL" \
  --control-plane-url "$DUAL_LINEAGE_CONTROL_PLANE_URL" \
  --operator-secret "$DUAL_LINEAGE_NODE_OPERATOR_SECRET" \
  --output evidence/node-001-e2e.json
```

Treat a passing artifact as one part of the physical-node release gate. The
separate fallback proof requires a change-controlled node stop, confirmation
that the control plane marks the node offline, and evidence that deterministic
fallback is selected. Do not automate that stop from this tool.

Evidence files are operational records, not source inputs: store them in the
approved evidence system and never commit them to this repository.
