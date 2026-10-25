# HQ Core container startup contract (candidate only)

The pinned Core source exposes the ASGI application at
`dual_lineage.main:app` (`apps/api/src/dual_lineage/main.py`).
Its Python project declares `uvicorn[standard]` and FastAPI.

## Minimal, isolated startup

A Core-only image can launch the Python HTTP API without pretending to
orchestrate the three independent Ruby services:

```sh
exec python -m uvicorn dual_lineage.main:app --host 0.0.0.0 --port 8000
```

Use the exec form as the container's sole foreground process, so termination
signals reach the server. Bind to port 8000. No background daemons, implicit
database migrations, auto-enablement of provider calls, or secrets embedded in
the image. The Ruby RAG, Control, and Worker services remain separately
owned by Workloads; their health and integration require independent checks.

## Acceptance and compatibility

- Confirm the exact pinned Core commit and the dependency installation.
- Run `python -c 'from dual_lineage.main import app; assert app is not None'`
  inside an isolated image, then start the container and probe a documented
  HTTP endpoint. A successful import alone does not prove readiness.
- Preserve existing environment-based configuration, security middleware,
  authentication and rate limiting. Do not invent a health endpoint.
- Test graceful SIGTERM shutdown and failure when mandatory configuration is
  missing. No database schema changes during startup.
- If the release needs a combined Ruby/Python process supervisor, require a
  separate reviewed architecture decision and explicit lifecycle tests;
  do not recreate an unknown `start-dual-lineage.sh` by guesswork.
- Publish immutable image digests and have Octopus independently verify
  provenance and runtime acceptance before release promotion.

**Status:** contract defined from pinned source inspection; runtime behavior
and container build remain unverified. This is not a production activation.
