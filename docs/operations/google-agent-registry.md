# Google Agent Registry operating runbook

Status: implemented locally; deployment and live E2E remain unverified

The independent merge units and their evidence boundaries are tracked in the
[incremental merge ledger](google-agent-registry-merge-plan.md).

AyahOS remains authoritative for policy, execution, and evidence. Google Agent
Registry is used only as a discovery catalog. The Compute Registry, Undermind,
Action Gateway, and Shared Spine retain their existing ownership.

## Preflight

Run these read-only checks with the intended operator account:

```powershell
gcloud auth list --format='json(account,status)'
gcloud config get-value project
gcloud services list --enabled --filter='config.name:agentregistry.googleapis.com' --format='value(config.name)'
gcloud agent-registry agents search `
  --project="$AYAHOS_GCP_PROJECT_ID" `
  --location=global `
  --search-string="ayahos" `
  --format=json
```

The bounded repository smoke wrapper runs the same read-only search and
summarizes only the count and resource names:

```powershell
python scripts/google_agent_registry_readonly_smoke.py `
  --project="$AYAHOS_GCP_PROJECT_ID" --location=global --search-string=ayahos
```

Record the account, project, location, timestamp, and result. Do not print or
commit tokens or service-account keys. The current repository evidence is
retained in [`google-agent-registry-bootstrap-2026-10-22.md`](../infrastructure/google-agent-registry-bootstrap-2026-10-22.md).

Before any write, independently confirm project identity, residency, billing
posture, IAM scope, and the nonproduction target. Runtime discovery should use
viewer access; only the controlled publisher should receive editor access.

The repository helper is dry-run by default and never creates keys:

```powershell
python scripts/bootstrap_google_agent_registry.py --project="$AYAHOS_GCP_PROJECT_ID"
```

Use `--apply` only after reviewing the project and intended identities. The
apply path creates the viewer/publisher service accounts and role bindings;
it does not create credentials or register capabilities.

## Configuration

The four switches are independent and default to `false`:

| Switch | Effect |
| --- | --- |
| `DUAL_LINEAGE_REGISTRY_DISCOVERY_ENABLED` | Permit read-only discovery |
| `DUAL_LINEAGE_REGISTRY_PUBLISHING_ENABLED` | Permit guarded additive publishing |
| `DUAL_LINEAGE_REGISTRY_ROUTING_ENABLED` | Permit shadow/canary proposals |
| `DUAL_LINEAGE_REGISTRY_EXECUTION_ENABLED` | Satisfy the final execution prerequisite |

Set `DUAL_LINEAGE_REGISTRY_BASE_URL` only to an HTTPS endpoint. Store
`DUAL_LINEAGE_REGISTRY_TOKEN` in a protected provider secret store. The local
configuration check does not contact Google and never prints the token:

```powershell
make registry-config-check
```

## Promotion gates

1. Offline: run manifest, adapter, reconciliation, authorization, shadow,
   publisher, rollout, and Spine tests.
2. Staging read-only: enable discovery only; verify authenticated search and
   signed local fallback. Normal chat must remain functional during outage.
3. Shadow: enable discovery and routing; compare proposals with existing
   routing, but keep execution disabled.
4. Canary: use only independently approved, read-only capabilities; require
   operator allowlist, intent-binding checks, Action Gateway authorization, and
   zero bypasses.

Ruby maintenance owns only the bounded `registry_reconcile` job. It consumes
already-fetched local and remote inventory, returns an additive plan, and marks
missing entries for review. It must not make an authorization decision, invoke
an Action Gateway tool, or delete a registry entry.

Authenticated staging discovery is available at
`GET /v1/runtime/agent-registry/discover?q=...` and through the Admin
operator proxy. It is read-only and returns normalized metadata only; the
feature switch must be enabled explicitly.

The current runtime attaches this service to the authenticated Admin inventory
and discovery surface. It is not on the normal user-request routing path, and
the tested shadow selector and Action Gateway binding do not make a registry
capability executable by themselves.

Offline fallback uses `DUAL_LINEAGE_REGISTRY_SNAPSHOT_PATH` plus the protected
`DUAL_LINEAGE_REGISTRY_SNAPSHOT_KEY`. Runtime startup verifies the HMAC before
attaching the adapter; incomplete or invalid snapshot configuration disables
the registry service.

The guarded publisher currently supports Google manual registration through a
`Service` resource for approved `NO_SPEC` agents. The endpoint URL must come
from a separate operator-supplied HTTPS mapping; it is never taken from remote
catalog metadata. Other Google spec kinds fail closed until their exact payload
contract is separately reviewed.
5. Production: promote one bounded capability at a time with source SHA,
   manifest digest, rollout flags, smoke result, and rollback record.

No stage promotes because a registry object says it is safe. Each candidate
must pass local manifest validation, operator approval, deterministic
Undermind checks, and Action Gateway reauthorization.

## Rollback

Disable the affected switch, restore the last approved local snapshot, and
verify the normal chat path. Rollback must not require Google availability.
Publishing is additive by design; missing remote entries become review items,
never deletion commands.

## Evidence checklist

For each promotion record:

- environment and timestamp;
- exact source commit SHA;
- rollout switch values;
- approved manifest digest;
- CI result with required lanes and no unexplained skips;
- authenticated request path and observed result;
- Shared Spine observation ID or event sequence;
- rollback result and remaining limitations.

Local tests and configuration are not hosted CI, deployment, or live proof.
