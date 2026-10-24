# Organization-wide Gemini CLI on Octopus

## Scope and isolation

Five private repositories: `ayahos-site`, `ayahos-core`, `ayahos-admin`, `ayahos-platform`, and `ayahos-workloads`. Each contains a `GEMINI.md` with repository-specific review boundaries. One central runner is maintained at `scripts/ci/octopus_gemini_org_review.sh` in `ayahos-platform`; do not fork it into five copies.

**Proposed separate Octopus resources:**

- Project: `AyahOS HQ Gemini Review`
- Environment: `HQ-Gemini-CI`
- Lifecycle: `AyahOS HQ Gemini CI Only` with one phase, one environment
- Octopus space: `Spaces-1`
- Project-only sensitive variable: `GEMINI_API_KEY`
- Explicit runtime inputs: `OCTOPUS_PROJECT_NAME`, `OCTOPUS_ENVIRONMENT_NAME`, `REVIEW_REPOSITORY`, `REVIEW_SHA`, `REVIEW_PROMPT`

The existing `AyahOS`, `AyahOS HQ Verification`, `Development`, `Staging`, `Production`, and `Portfolio-CI` resources must remain unchanged. This Gemini project is advisory only; deterministic CI stays in its existing verified pipelines. Run manually at first; no shared organization-wide webhook, no automatic merging.

## Required provisioning and acceptance

1. Create the new isolated environment, lifecycle, and project in Octopus. Set a **project-scoped sensitive** Gemini API key. Do not copy the AyahOS production or portfolio API keys.
2. Configure a trusted Git repository source pointing at `ayahos-hq/ayahos-platform` and a reviewed SHA. Run on an isolated hosted Ubuntu worker with Node.js and npm available.
3. Configure the runner as a manual optional script step. Map Octopus's built-in project and environment names to the two required runtime variables. Explicitly allowlist the five repositories and validate the exact SHA.
4. **Before claiming real code review**, add a read-only, narrowly scoped GitHub App or installation credential that can retrieve the exact pinned commit/diff from the private target repository. Feed the retrieved, size-limited diff as untrusted review data to Gemini. The current script validates repository and SHA but does **not** retrieve source/diff, so its output is only an advisory *metadata-level* analysis until that adapter exists.
5. Verify an actual Gemini invocation with redacted logs, authenticated source access, a concrete file-level finding, and a clean zero-secret trace. Verify the exact reviewed SHA and report failures as failures.
6. Preserve mandatory tests and branch protections. Never replace test success with a Gemini opinion. No production deployment is part of this integration.

## Current state

Repository-side configuration is committed on review branches only. The new Octopus project, environment, lifecycle, sensitive API key, read-only private-repo access, real Gemini inference, and production-ready review adapter are **not verified**. Do not treat this documentation or a passing syntax check as operational activation.
