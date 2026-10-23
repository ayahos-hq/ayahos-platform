# AyahOS Platform — provisional source extraction

**Status: public by owner decision, provisional source extraction, not deployed and not production authority.** This repository is a staging home for CI/CD orchestration, Octopus project definitions, deployment templates, release checks and infrastructure records. Do not connect Octopus, GitHub webhooks, Cloudflare or any production service to this repo until the migration gates are complete. Treat all repository contents as public; secrets belong exclusively in managed secret stores.

## Pinned import

- Original: `fuaadabdullah/AyahOS_Dual_Lineage` at `a7ef41fe1ec6a680bc734a5d54890fb13972d3a3`.
- **61 source blobs** copied exactly with original executable modes under `.octopus/`, `deploy/`, `scripts/ci/`, `docs/infrastructure/`; LICENSE and NOTICE carried over.
- Source file identities and Git modes are recorded in `SOURCE-PROVENANCE.json`.
- This snapshot **retains legacy monorepo-relative script paths and service references**; it is not a deployable multi-repo pipeline.
- Existing Cloudflare Pages and Vercel rollback remain unchanged; Overmind/Undermind/Spine authority stays in the source backend.

## Safe independent checks

From this repository:
```sh
python3 scripts/verify-platform.py
node --test deploy/octopus-github-bridge/test/worker.test.js
find scripts/ci -type f -name '*.sh' -exec bash -n '{}' \;
```
These inspect source identity, CI topology and the webhook bridge's local mocked behavior. They do **not** create Octopus releases, connect to GitHub status APIs, deploy containers, load secrets, test PostgreSQL, or certify the source's complete eight-lane Octopus runtime. That remains a separate authenticated integration/release gate.

The upstream `deploy/octopus-github-bridge/wrangler.jsonc` still targets the original monorepo; **do not run `wrangler deploy` from here.** Even if documentation describes an existing deployed Worker, that refers to an earlier service configuration, not deployment from this new repository.

## Live bridge ownership (checked 2026-10-23)

The existing endpoint is `https://ayahos-octopus-github-bridge.fuaadabdullah.workers.dev`.
Its live `GITHUB_REPOSITORY` is `fuaadabdullah/AyahOS_Dual_Lineage`; its Octopus project
`AyahOS` sources that monorepo and deploys to `Development`. The Worker has encrypted
`OCTOPUS_API_KEY` and `GITHUB_WEBHOOK_SECRET` bindings. After rotating the webhook secret,
pings from both the monorepo and `ayahos-hq/ayahos-platform` returned HTTP 200. A ping proves
webhook delivery, **not** that a push was accepted or a release ran. HQ pushes are currently
ignored by the shared Worker, and no HQ Octopus release or passing `octopus/verify` status
was established. The copied bridge README is pinned source evidence, not current HQ operating
instructions.

Do not repoint or redeploy the shared Worker for HQ: doing so would interrupt the monorepo
release path. HQ needs a separate Octopus project connected to this repository, checks that
fetch exact manifest-pinned component SHAs rather than assuming a monorepo checkout, and a
separate Worker with its own KV and scoped credentials. Sealed credentials cannot be copied
out of the existing Worker; provision new values directly in the new secret store. Until
those gates pass, the existing endpoint's `/status/<sha>` is not HQ release evidence. Review
exact-SHA results manually before merge or cutover; no enforced HQ required-check gate has
been demonstrated.

## Operator-only three-way drift evidence (no new CI credential)

The four HQ sibling repos are private. Do not add a broad persistent Actions
token merely to audit them. With an existing authenticated `gh` operator login,
run from this repository:

```sh
python3 -m unittest discover -s scripts -p 'test_audit_repo_drift.py' -v
python3 scripts/audit-repo-drift.py --auth gh --output drift-report.json
python3 scripts/audit-repo-drift.py --auth gh --enforce
```

The `--auth gh` option uses the operator's existing GitHub CLI identity and
does not accept or print credentials. CI tests the read-only client with mocks,
not private repository reads. A nonzero exit blocks source promotion, and zero
only establishes the scanned Git tree state, **never** Octopus/live release
acceptance. Do not commit generated private-repository path reports to the public
platform repo.

## Immutable HQ candidate source assembly (non-deployable)

After resolving a platform release candidate SHA (the **full** 40-character commit
containing the exact `release-manifest.json`), an authorized operator can stage the
five *private* repositories into a **new** temporary workspace using their existing
`gh auth login` identity. No long-lived GitHub token or extra cloud runtime is
created:

```sh
python3 scripts/assemble-hq-workspace.py \
  --manifest release-manifest.json \
  --platform-head FULL_PLATFORM_COMMIT_SHA \
  --workspace /tmp/ayahos-hq-candidate
```

Choose an unused workspace path. The script refuses to overwrite anything, clones
each exact component SHA detached, checks actual `HEAD` and tracked/untracked state,
and verifies that the pinned platform manifest matches the supplied file byte-for-byte.
A partial failure deletes its own staging tree. An atomic completed directory contains
`CANDIDATE-SOURCE-EVIDENCE.json`, which is **source identity evidence only**; it
never claims that release packages have been built, nor that Octopus, database restore,
authenticated chat or rollback checks have passed. Do not put private source reports
in this public repository. This is preparation for an independent HQ Octopus project,
**not** permission to repoint the existing production bridge or deploy.

See `MIGRATION-GATES.md` and master [migration issue #243](https://github.com/fuaadabdullah/AyahOS_Dual_Lineage/issues/243).
