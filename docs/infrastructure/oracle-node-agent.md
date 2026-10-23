# AyahOS Oracle Servers: cognitive node

Oracle is a separate cognitive target, not Node 1 and not the Render runtime. The
supported deployment runs the repository node agent beside the private `goblin-core`
llama.cpp service and advertises only `oracle-heavy` with the `cognitive` role.

The checked-in service template is `deploy/oracle/goblin-oracle-node.service` and the
redacted environment contract is `deploy/oracle/oracle-node.env.example`. The agent
must register through the normal `/compute/nodes/heartbeat` protocol before the
control plane can select it.

## Activation requirements

1. Install the lightweight API runtime dependencies in `/opt/goblin/venv`.
2. Deploy this repository at `/opt/goblinos-dual-lineage`.
3. Configure `/etc/goblin/oracle-node.env` with separately managed registration and
   inference secrets.
4. Configure a separate HTTPS hostname such as
   `oracle-129.213.50.249.nip.io` to proxy to `127.0.0.1:8112`.
5. Add that hostname to `DUAL_LINEAGE_NODE_ENDPOINT_ALLOWLIST` on the control plane.
6. Verify `/health` reports `backend: reachable` and `registration.ok: true`. On the
   control plane, `GET /compute/nodes` (operator secret) should list `oracle-heavy` as
   `online` with only the `cognitive` role and the configured model id. Then confirm one
   cognitive inference succeeds.

The node reports `degraded` while its backend is down, and the control plane stops
selecting it until the backend answers again. The control plane pins `oracle-heavy` to
the `cognitive` role, so autonomic (critic) work never reaches it.

To take the node out of routing, set `DUAL_LINEAGE_NODE_ADMIN_SECRET` and call
`POST /admin/drain` on the node. Forgetting the node on the control plane does not
work, because its next heartbeat re-registers it within the heartbeat interval.

The service intentionally has no autonomic model, no action gateway access, and no
write/exec/network authority beyond the outbound heartbeat and llama.cpp request.
Missing secrets or an unallowlisted endpoint must prevent registration rather than
falling back to an insecure default.
