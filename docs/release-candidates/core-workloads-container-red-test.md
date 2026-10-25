# HQ container composition: regression contract (candidate context implemented)

This document records the former Core-only Dockerfile failure and the reviewed
source-composition contract. The platform branch now has an exact-SHA composer
and a candidate composite startup contract, but it must remain **RED for
release** until an isolated Linux image build, immutable OCI digest, and runtime
acceptance gates produce independent evidence.

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

1. The source context is assembled from **exactly** the Core and Workloads SHAs
   in `release-manifest.json`; no mutable branch references or untracked files.
2. The context contains all three Ruby application directories and a reviewed,
   executable startup script, with collision handling that fails closed.
3. The context records immutable provenance for **both** component SHAs and the
   complete five-repository candidate; a single image revision label cannot
   attest two sources.
4. An isolated Linux build succeeds; container startup and health checks pass.
5. Tampering with either input SHA, missing Ruby directory, missing startup
   script, or a path collision produces a nonzero result.
6. Image digest is captured from the registry and independently rechecked by
   Octopus. A source archive digest must never be substituted for an OCI digest.

## Current result

**SOURCE CONTEXT GREEN / RUNTIME RED:** the composer and offline regression
suite cover the exact-source, required-path, provenance, and fail-closed
composition checks. Requirements 4–6 still require a real isolated container
build, startup/health evidence, registry digest capture, and independent
Octopus recheck. This is not an acceptance certificate.
