# Platform extraction acceptance gates

The original monorepo is canonical until all explicit gates pass. This snapshot never modifies a live Octopus project.

1. **Integrity and privacy:** Verify 66 tracked platform source blobs and their Git modes; audit any executable/script edits and scan for accidental credentials. Example .env templates have empty values. Never move existing secret values into Git.
2. **Isolated verification:** Validate Octopus process syntax/structure, required steps and script paths, bash syntax, JSON service inventory, and local-only Node mocked tests for the GitHub/Octopus bridge. No live webhooks or API tokens in CI.
3. **Cross-repository contract:** Build a version-pinned manifest for \`ayahos-core\`, \`ayahos-site\`, \`ayahos-admin\`, and \`ayahos-workloads\`; replace monorepo-relative references with checked-out artifacts from immutable SHAs. Preserve Octopus release authority and hard fail-closed gates, including PostgreSQL 16 with real pgvector, Ruby RAG/worker/control and deterministic policy tests.
   `release-manifest.json` is the candidate manifest. It binds four exact repository HEADs plus an immutable platform source parent (the manifest is stored in the platform repository, so its own commit is intentionally checked by ancestry); artifact digests and live acceptance remain explicitly pending until independently produced and verified.
4. **Cost and operations:** Resource-cap CI lanes on GitHub Free and Octopus; verify an explicit zero-overage setting from the account billing UI rather than assuming hosted CI is cost-free. Heavy model/DB workloads must not run on undersized free-tier web instances.
5. **Secret handling:** Scope a new bridge webhook/signing key and token if a new GitHub integration is intentionally created. Configure those only as managed secrets with least permissions. Preserve the current bridge and GitHub status context until new statuses prove authoritative.
   The live bridge still routes the original monorepo to its Octopus project. A successful HQ
   webhook ping does not authorize treating that bridge's status as HQ verification; use a
   separate project and bridge after the exact-SHA cross-repository checks exist.
6. **Real verification:** Run the exact approved Octopus revision end to end on an authorized worker, record all required step outcomes and container digests. Never silently replace pgvector with SQLite or skip critical gate failures after exit 137.
7. **Cutover:** Separate pre-prod testing from protected production update. Require user-authorized destination and credentials steps, signed rollback plan, correct deployed SHAs, and post-deploy SSE/chat, trace, auth and failure probes. Keep Cloudflare primary, Vercel rollback and old monorepo CI until cutover is proven.

**No Octopus project, external webhook, Render, Cloudflare, Vercel, DNS, secrets or Google Cloud modifications are part of this PR.**

## Evidence checkpoint: 2026-10-27

The separate HQ verification project exists (`Projects-21`). Its release `0.0.18`
/ task `ServerTasks-1944` succeeded on 2026-10-24, but covers three configured
steps using older Platform plus Core sources. Site, Admin and Workloads are
absent from that process's source coverage. This is preliminary verification,
not completion of gates 3, 6 or 7.

[Draft PR #42](https://github.com/ayahos-hq/ayahos-platform/pull/42), implementation
commit `1b660ff7fb2a50e22c28d996c78e86ada985f7d0`, passed
[hosted offline verification](https://github.com/ayahos-hq/ayahos-platform/actions/runs/40465404016)
(64 tests, 26 mocked bridge tests, source/manifest and shell checks). The separate
`Workers Builds: ayahos-hq-verification-bridge` check failed. Its cause remains
undiagnosed; no successful deployment is inferred.

Branch protection requires `octopus/hq-operator-verified`; no status under that
context was observed for the implementation commit. Offline CI does not satisfy
the Octopus gate. Later documentation commits require their own CI results.

The [read-only audit](scripts/audit-octopus-release.py) detects stale, partial,
disabled or skipped source evidence, and never attests production acceptance.
All five clean candidate repositories assembled locally. Hosted five-component
integration, eight-lane outcomes, artifact digests, PostgreSQL/pgvector, recovery,
authenticated smoke and rollback remain pending. Preserve the shared monorepo
project and bridge. Do not close issues #6 or #35 based on these partial results.

See the [append-only task record](docs/release-candidates/octopus-gap-remediation-20261027.md)
for exact identities, local limitations and the order of observations.
