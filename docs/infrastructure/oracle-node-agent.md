# AyahOS Oracle Servers: cognitive node

Oracle is a separate cognitive target, not Node 1 and not the Fly Control Hub.
Fly (`ayahos-control-api.fly.dev`) only routes. Inference stays on Oracle or
Node 1. The supported deployment runs the HQ node agent beside the private
llama.cpp service and advertises only `oracle-heavy` with the `cognitive` role.

Canonical templates live in `ayahos-hq/ayahos-platform`:
`deploy/oracle/goblin-oracle-node.service` and
`deploy/oracle/oracle-node.env.example`. The agent must register through
`/compute/nodes/heartbeat` before Core can select it.

## Activation requirements

1. Install the lightweight API runtime dependencies in `/opt/goblin/venv`.
2. Prefer HQ `ayahos-core` as the agent source; a host path of
   `/opt/goblinos-dual-lineage` is historical, not the canonical owner.
3. Configure `/etc/goblin/oracle-node.env` with separately managed registration and
   inference secrets that match Fly.
4. Caddy on the Oracle host:
   - `oracle-129.213.50.249.nip.io` → `127.0.0.1:8112` (oracle-heavy)
   - `129.213.50.249.nip.io` → `127.0.0.1:18110` (SSH relay to Node 1 on 8110).
     Do not point this vhost at 18111; that port is not the live relay.
5. Add those hostnames to `DUAL_LINEAGE_NODE_ENDPOINT_ALLOWLIST` on Fly if the
   allowlist is enabled.
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
