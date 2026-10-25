# HQ container composition: regression contract (RED)

This test documents the known failure of the pinned extracted Core Dockerfile.
It must remain a **failing test** until the build context and startup contract
are implemented. Do not change the existing production Dockerfile to hide it.

## Reproduction

At the manifest-pinned commits, the Core Dockerfile uses `COPY . .` and then
executes `bundle install` in these paths:

- `apps/rag-ruby`
- `apps/control-ruby`
- `apps/ruby_worker`

The paths belong to Workloads, not the standalone Core checkout. Its CMD
references `/app/scripts/start-dual-lineage.sh`, which is not in the pinned
extracted source trees. A Core-only build therefore cannot satisfy the declared
filesystem contract.

## GREEN acceptance criteria

1. The build context is assembled from **exactly** the Core and Workloads SHAs
   in `release-manifest.json`; no mutable branch references or untracked files.
2. The context contains all three Ruby application directories and a reviewed,
   executable startup script, with collision handling that fails closed.
3. The image exposes an immutable provenance record for **both** component SHAs;
   a single `org.opencontainers.image.revision` label cannot attest two sources.
4. An isolated Linux build succeeds; container startup and health checks pass.
5. Tampering with either input SHA, missing Ruby directory, missing startup
   script, or a path collision produces a nonzero result.
6. Image digest is captured from the registry and independently rechecked by
   Octopus. A source archive digest must never be substituted for an OCI digest.

## Current result

**RED / BLOCKED:** requirements 1–6 have not been demonstrated in a real
container build. This is a test specification, not an acceptance certificate.
