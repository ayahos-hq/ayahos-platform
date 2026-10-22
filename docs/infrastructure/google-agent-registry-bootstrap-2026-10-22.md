# Google Agent Registry bootstrap evidence

Status: verified-local/read-only external preflight; no mutation performed

Timestamp: 2026-10-22 (America/New_York)

## Observed identity and API state

- Active Google account: `ayahos.dev@gmail.com`
- Selected project: `project-eec9b975-b6bd-4b41-bad`
- Enabled service: `agentregistry.googleapis.com`
- Registry location queried: `global`
- Search term: `ayahos`
- Search result: `{}` (no matching registered agents)

The read-only commands were `gcloud auth list`, `gcloud config get-value
project`, `gcloud services list --enabled`, and:

```powershell
gcloud agent-registry agents search `
  --project='project-eec9b975-b6bd-4b41-bad' `
  --location=global `
  --search-string='ayahos' `
  --format='json'
```

## Boundary of this evidence

This proves CLI authentication, project selection, API enablement, and a
successful read-only search request at the observed time. It does not prove
that the project is the final production project, that billing or residency
requirements are approved, that a publisher identity exists, or that any
capability is approved for AyahOS execution. No agent, MCP server, endpoint,
skill, IAM binding, secret, or deployment was created or changed.

The next safe bootstrap action is to confirm the project and location decision
with the operator, then test a nonproduction registration through a narrowly
scoped publisher identity. Runtime discovery must remain viewer-only.

## Read-only refresh

Observed later on 2026-10-22 from the same clean integration worktree:

- `ayahos.dev@gmail.com` remained the active account.
- `project-eec9b975-b6bd-4b41-bad` remained the selected project.
- `agentregistry.googleapis.com` remained enabled.
- The global `ayahos` search still returned `{}`.

This refresh changed no Google Cloud state and does not prove publisher IAM,
nonproduction registration, deployment, or live execution authorization.

## IAM observation

The active human account was returned with `roles/admin` and `roles/owner` on
the selected project. This is sufficient evidence for the observed read-only
CLI calls, but it is deliberately not a runtime authorization design. A
dedicated viewer identity and a narrowly scoped publisher identity remain
unverified and must be established before automation or registration writes.

## Service-account observation

The selected project currently lists one enabled service account,
`ais-gemini-key-9ec80495f516444@1086186141421.iam.gserviceaccount.com`. No
project IAM bindings containing an Agent Registry role were returned. This
account is treated as unrelated and was not reused; no service account, role,
key, or credential was created or changed.

The repository read-only smoke wrapper also ran successfully on Windows
against the selected project and `global` location. It reported
`inventory_count=0`; it made no write calls and printed no credentials.
