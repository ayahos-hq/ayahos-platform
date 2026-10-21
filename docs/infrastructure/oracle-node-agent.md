# Oracle cognitive node

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
6. Verify `/health`, the heartbeat registry entry, and a cognitive inference before
   enabling Oracle in production routing.

The service intentionally has no autonomic model, no action gateway access, and no
write/exec/network authority beyond the outbound heartbeat and llama.cpp request.
Missing secrets or an unallowlisted endpoint must prevent registration rather than
falling back to an insecure default.
