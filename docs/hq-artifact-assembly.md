# AyahOS HQ: verified artifact assembly and Octopus release authority

Status: feature-branch implementation; NO production cutover or live verification.

## Design

Continue using the existing five-repo assembler. The immutable candidate manifest stays in the ayahos-hq/ayahos-platform repository. The full platform HEAD SHA must be supplied explicitly (never main), and its embedded platform manifest SHA must be an ancestor. All four sibling repository HEADs must exactly match their pins. The original fuaadabdullah/AyahOS_Dual_Lineage repository remains the canonical production source.

On a trusted Linux machine with authorized access to all five repositories:

~~~sh
python3 scripts/assemble-hq-workspace.py \
  --manifest release-manifest.json \
  --platform-head FULL_PLATFORM_HEAD_SHA \
  --workspace /private/new-hq-workspace

python3 scripts/build-hq-artifacts.py \
  --manifest release-manifest.json \
  --workspace /private/new-hq-workspace \
  --output /private/new-hq-artifacts

python3 scripts/build-hq-artifacts.py \
  --verify-only --output /private/new-hq-artifacts
~~~

The new builder revalidates the existing source verifier and the assembler receipt, checks the five actual detached commit SHAs, verifies the platform manifest byte for byte, and builds deterministic Git archives. It emits SHA-256 and size evidence for exactly five source tar files, then independently verifies them. Symlink escapes, untrusted receipts, changed commits, path traversal, missing input and overwrite attempts fail closed. Temporary partial output is removed. Archives contain private source: never commit these generated outputs to this public repository.

## Core + Workloads composite context

The source assembler is followed by scripts/hq/compose-hq-runtime.py. It
revalidates the clean exact-SHA workspace, copies only apps/api from Core and
apps/rag-ruby, apps/control-ruby, and apps/ruby_worker from Workloads, and
adds the reviewed scripts/hq/Dockerfile.hq-composite plus
scripts/hq/start-hq-composite.sh. Any missing path, symlink, special file,
collision, dirty checkout, receipt mismatch, or platform-manifest mismatch
blocks composition.

The candidate public listener is the Python FastAPI application on port 8000.
Ruby remains internal bounded support: RAG on 8102, control transport on 8103,
and an optional worker role. The entrypoint performs no migrations and tears
down the stack if a required child exits. The generated
COMPOSITE-SOURCE-MANIFEST.json records the manifest digest, the platform
checkout SHA, all four sibling pins, and the authority contract: Python owns
deterministic Undermind, authorization, quota admission, routing, interrupts,
Action Gateway, and Shared Spine; Ruby owns transport/workflow/RAG only.
Provider calls are forbidden in Site, Admin, and Workloads. Overmind and
advisory-Undermind RAG corpora remain separate, and external RAG text remains
untrusted data.

The composer is still a source-context gate. It is not a successful container
build, image provenance attestation, deployment, or release approval.

## Container digest pinning (separate acceptance layer)

Source tarball checksums are NOT OCI image digests or application build evidence. An optionally supplied OCI lock file must name the built image by full immutable registry manifest digest and matching source commit. Example of structure (placeholder deliberately NOT executable):

~~~json
{
  "images": [
    {
      "component": "ayahos-core",
      "source_sha": "ce43a6c99b2f80bc6f0b4903687373e2d007daff",
      "reference": "registry.example.invalid/ayahos/core@sha256:REPLACE_WITH_64_HEX_DIGEST"
    }
  ]
}
~~~

After Octopus builds and publishes an image with OCI config label org.opencontainers.image.revision equal to the exact source commit, use:

~~~sh
python3 scripts/build-hq-artifacts.py --manifest release-manifest.json \
  --workspace /private/new-hq-workspace \
  --output /private/new-hq-artifacts-with-oci \
  --oci-lock /private/oci-lock.json
~~~

Skopeo reads the registry image manifest bytes, verifies their actual SHA-256 against the locked reference, and checks the image config revision label. Missing registry access, mismatched bytes, a mutable tag, invalid source SHA or missing revision label blocks the build. The extracted core Dockerfile remains an invalid standalone multi-repo build. The reviewed composite Dockerfile has the required provenance labels, but no verified OCI digest exists until Octopus performs the isolated image build and registry retention step. OCI identity and claimed source consistency still require trustworthy Octopus image-build logs and immutable artifact retention before release approval.

## Composite image provenance

The reviewed composite Dockerfile carries separate labels for the Core SHA,
Workloads SHA, Platform checkout SHA, and release-manifest digest. When the
Octopus image-build step has published the image, set
`HQ_RUNTIME_IMAGE_REF` to its full immutable `repository@sha256:<64 hex>`
reference. The existing builder then reads the registry manifest bytes and
image config with Skopeo and blocks unless the digest and every lineage label
match the exact assembled candidate. A source tar checksum cannot satisfy this
check. If the variable is absent, runtime-image evidence remains explicitly
pending and cannot authorize promotion.

## Single pipeline authority: Octopus

Keep the existing Octopus Deploy product, existing monorepo project, production sources, GitHub bridge and octopus/verify context unchanged. Configure a separate, restricted AyahOS HQ Verification project in Octopus only after authorized review. This is project isolation within Octopus, not a new release framework or a second CI provider.

Its mandatory Git-backed artifact step is scripts/octopus/hq-artifact-gate.sh. It requires Octopus.Project.Name to be AyahOS HQ Verification, an explicit HQ_PLATFORM_SHA matching Octopus.Release.Git.CommitHash, and authorized read access to the four private sibling repositories. It runs the pre-existing offline platform suites, the existing source assembler, the builder and the independent checksum verifier. Octopus retains only its evidence JSON, not the private source tar files. The script does not mark a release or post a GitHub success status.

Additional mandatory Octopus checks before any success status or cutover:
1. Actual source SHA, manifest SHA-256, five archive checksums, and OCI registry digests tied to the same release.
2. Core deterministic authority, API and cross-language contracts, site/admin SSE and auth, ML, Ruby worker and control suites, all with zero required-test skips.
3. Isolated PostgreSQL 16 + real pgvector, schema v23 and Ruby RAG integration with exit-code and resource evidence.
4. Database backup restoration into a disposable instance with integrity and rollback checks.
5. Staging authenticated chat, provider failover, SSE, policy-denial and telemetry probes against the exact image digests.
6. Known-good digest rollback rehearsal and explicitly approved canary.
7. Every Octopus required task step actually passes. Only a dedicated HQ-scoped reporter may post status to the exact HQ platform commit. Missing and skipped required steps count as failure.

The extracted legacy Octopus eight-step process still references monorepo paths and cannot prove this multi-repo release. No GitHub Actions or other CI should become competing release authority. Existing informational PR checks are useful but are not Octopus acceptance.

## Truthful status

The branch implements local artifact generation, checksum verification, optional live-registry OCI digest checks, a proposed HQ Octopus entrypoint and regression tests. The real private five-repo assembly, actual image digests, authenticated Octopus project/run/status authority, PostgreSQL recovery, live smoke and rollback remain unverified. HOLD production deployment and cutover until independent evidence passes.

## Inspected standalone-image blocker

The current ayahos-hq/ayahos-core Dockerfile copies only the core checkout but then runs Bundler in apps/rag-ruby, apps/control-ruby and apps/ruby_worker. Those directories live in the separately pinned ayahos-workloads repository, not core. Its CMD also references scripts/start-dual-lineage.sh, absent from the core, platform and workloads current source trees. Therefore the extracted core Dockerfile is **not a verified standalone multi-repo build**. Resolve the explicit composition/startup contract, then build on an isolated worker and record the actual image registry digests; do not report these source archives as deployable images.
