# Platform extraction acceptance gates

The original monorepo is canonical until all explicit gates pass. This snapshot never modifies a live Octopus project.

1. **Integrity and privacy:** Verify 49 original source blobs and their Git modes; audit any executable/script edits and scan for accidental credentials. Example .env templates have empty values. Never move existing secret values into Git.
2. **Isolated verification:** Validate Octopus process syntax/structure, required steps and script paths, bash syntax, JSON service inventory, and local-only Node mocked tests for the GitHub/Octopus bridge. No live webhooks or API tokens in CI.
3. **Cross-repository contract:** Build a version-pinned manifest for \`ayahos-core\`, \`ayahos-site\`, \`ayahos-admin\`, and \`ayahos-workloads\`; replace monorepo-relative references with checked-out artifacts from immutable SHAs. Preserve Octopus release authority and hard fail-closed gates, including PostgreSQL 16 with real pgvector, Ruby RAG/worker/control and deterministic policy tests.
4. **Cost and operations:** Resource-cap CI lanes on GitHub Free and Octopus; verify an explicit zero-overage setting from the account billing UI rather than assuming hosted CI is cost-free. Heavy model/DB workloads must not run on undersized free-tier web instances.
5. **Secret handling:** Scope a new bridge webhook/signing key and token if a new GitHub integration is intentionally created. Configure those only as managed secrets with least permissions. Preserve the current bridge and GitHub status context until new statuses prove authoritative.
6. **Real verification:** Run the exact approved Octopus revision end to end on an authorized worker, record all required step outcomes and container digests. Never silently replace pgvector with SQLite or skip critical gate failures after exit 137.
7. **Cutover:** Separate pre-prod testing from protected production update. Require user-authorized destination and credentials steps, signed rollback plan, correct deployed SHAs, and post-deploy SSE/chat, trace, auth and failure probes. Keep Cloudflare primary, Vercel rollback and old monorepo CI until cutover is proven.

**No Octopus project, external webhook, Render, Cloudflare, Vercel, DNS, secrets or Google Cloud modifications are part of this PR.**
