# AyahOS Platform — provisional source extraction

**Status: public by owner decision, provisional source extraction with isolated HQ verification, not production authority.** This repository is a staging home for CI/CD orchestration, Octopus project definitions, deployment templates, release checks and infrastructure records. The separate HQ Octopus verification project exists; full multi-repository acceptance and production cutover remain pending. Production connections and changes require the migration gates and explicit authorization. Treat all repository contents as public; secrets belong exclusively in managed secret stores.

## Observed Octopus baseline (2026-10-27; build repair below)

[Draft PR #42](https://github.com/ayahos-hq/ayahos-platform/pull/42) contains the
verification coverage fixes and read-only release audit. Its implementation commit
is `1b660ff7fb2a50e22c28d996c78e86ada985f7d0`.

- **Hosted GitHub checks passed** for that commit in
  [run 40465404016](https://github.com/ayahos-hq/ayahos-platform/actions/runs/40465404016):
  64 offline tests without skips, source/manifest validation, shell syntax and
  26 mocked bridge tests. This establishes hosted offline verification.
- **Separate provider check failed:** `Workers Builds: ayahos-hq-verification-bridge`.
  Its root cause and live bridge state have not been established by this task.
  Do not describe the PR as fully green or infer a successful Worker deployment.
- **Live Octopus evidence:** isolated project `AyahOS HQ Verification`
  (`Projects-21`) release `0.0.18` / task `ServerTasks-1944` passed three configured
  steps on 2026-10-24. It selected older Platform commit
  `f01dcced85ea294bdcdacbebb0730dc6819aaa1d` and the pinned Core revision.
  Site, Admin and Workloads have no source steps in that process snapshot.
- **Required GitHub context:** `octopus/hq-operator-verified`. Its older success
  must not be reused for a newer SHA. No commit status was observed for `1b660ff`.
- **Still pending:** five-component hosted integration, all eight required lane
  outcomes, independent artifact digests, PostgreSQL/pgvector, isolated restore,
  authenticated smoke and rollback. No new Octopus run or live configuration
  change was performed by this task.

See the [append-only remediation record](docs/release-candidates/octopus-gap-remediation-20261027.md)
and [live source coverage audit](docs/release-candidates/octopus-source-coverage-20261027.json).
Results above apply to the named implementation commit, not automatically to
later documentation commits or future branch heads.

## Pinned import

- Original: `fuaadabdullah/AyahOS_Dual_Lineage` at `a7ef41fe1ec6a680bc734a5d54890fb13972d3a3`.
- **66 preserved source blobs plus three HQ build verification files** under `.octopus/`, `deploy/`, `scripts/ci/`, `scripts/db/`, `docs/infrastructure/`: 69 audited entries with recorded executable modes; LICENSE and NOTICE carried over.
- Source file identities and Git modes are recorded in `SOURCE-PROVENANCE.json`.
- This snapshot **retains legacy monorepo-relative script paths and service references**; it is not a deployable multi-repo pipeline.
- Existing Cloudflare Pages and Vercel rollback remain unchanged; Overmind/Undermind/Spine authority stays in the source backend.

## HQ Worker build repair (2026-10-27)

Authenticated dashboard inspection confirmed that the failing build switched
from its triggering commit to `feat/pinned-hq-artifact-assembly-20261025`, ran
from `/deploy/octopus-github-bridge`, and failed because the selected config
lacked a `previews` block. These are now confirmed observations rather than
an inference from the older access-reliability notes.

This branch integrates only the six HQ build-specific files from PR #38,
including the isolated configuration, exact-SHA preflight, tests and provenance
updates. The separate login/access-doctor changes are not included.
Local validation passed 69 offline tests, 26 mocked bridge tests, immutable
source and manifest checks, and Wrangler 4.152.0 dry-run packaging.

The authorized HQ-only dashboard repair uses repository root `/`, the
exact-SHA verification command and pinned preview command in
[BUILD_COMMANDS.md](deploy/hq-verification-bridge/BUILD_COMMANDS.md).
The production build command is a dry run; it does not release production code.
The preview uses dedicated TASKS KV `2b5af79207114dec9989bc1d952c3c9d`, distinct
from production `49ce086dc87f4de9a5110e5771907cb3`, and has no production
secrets or cron. Preview URLs are public. A preview `/healthz` response of 503
is expected while required API/webhook credentials remain absent.

New hosted build results must be recorded against their own exact revision.
These build checks do not establish eight-lane Octopus release acceptance.
The append-only task record contains the production baseline and subsequent
read-back/build results.

## Safe independent checks

From this repository:
```sh
python3 scripts/verify-platform.py
python3 scripts/verify-release-manifest.py
python3 scripts/run-hq-offline-tests.py
node --test deploy/octopus-github-bridge/test/worker.test.js
while IFS= read -r -d '' script; do
  bash -n "$script" || exit 1
done < <(find scripts/ci scripts/octopus -type f -name '*.sh' -print0)
```
These inspect source identity, CI topology and the webhook bridge's local mocked behavior. They do **not** create Octopus releases, connect to GitHub status APIs, deploy containers, load secrets, test PostgreSQL, or certify the source's complete eight-lane Octopus runtime. That remains a separate authenticated integration/release gate.

The upstream `deploy/octopus-github-bridge/wrangler.jsonc` still targets the original monorepo; **do not run `wrangler deploy` from here.** Even if documentation describes an existing deployed Worker, that refers to an earlier service configuration, not deployment from this new repository.

## Monorepo bridge ownership (historical check: 2026-10-23)

The existing endpoint is `https://ayahos-octopus-github-bridge.fuaadabdullah.workers.dev`.
Its live `GITHUB_REPOSITORY` is `fuaadabdullah/AyahOS_Dual_Lineage`; its Octopus project
`AyahOS` sources that monorepo and deploys to `Development`. The Worker has encrypted
`OCTOPUS_API_KEY` and `GITHUB_WEBHOOK_SECRET` bindings. After rotating the webhook secret,
pings from both the monorepo and `ayahos-hq/ayahos-platform` returned HTTP 200. A ping proves
webhook delivery, **not** that a push was accepted or a release ran. HQ pushes are currently
ignored by the shared Worker. That historical check did not establish an HQ release.
The separate HQ release and status context observed on 2026-10-27 are documented above.
The copied bridge README is pinned source evidence, not current HQ operating
instructions.

Do not repoint or redeploy the shared Worker for HQ: doing so would interrupt the monorepo
release path. HQ has a separate Octopus verification project but still needs checks that
fetch exact manifest-pinned component SHAs rather than assuming a monorepo checkout, and a
a verified separate Worker integration with its own KV and scoped credentials. The
failed HQ Workers build check does not establish its deployment or configuration.
Sealed credentials cannot be copied
out of the existing Worker; provision new values directly in the new secret store. Until
those gates pass, the existing endpoint's `/status/<sha>` is not HQ release evidence. Review
exact-SHA results before merge or cutover. Current branch protection requires
`octopus/hq-operator-verified`; that context is separate from the monorepo's
`octopus/verify` and from offline GitHub Actions.

## Read-only Octopus source coverage audit

With the existing authenticated Octopus CLI session, run from this repository:

```sh
python3 scripts/audit-octopus-release.py \
  --manifest release-manifest.json \
  --platform-sha FULL_PLATFORM_COMMIT_SHA \
  --release-id Releases-NUMBER \
  --task-id ServerTasks-NUMBER
```

Use the exact candidate Platform SHA containing the supplied manifest, not a
mutable branch name. The audit follows the release's immutable process snapshot,
links deployment and task identity, checks successful source-step outcomes, and
compares all five selected revisions. Exit `0` means source coverage only;
exit `1` means incomplete coverage; exit `2` means invalid evidence or a failed
read-only request. The report always keeps `production_accepted: false`.
It performs GET requests only, prints no credentials, and posts no GitHub status.

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
five repositories, including the private siblings, into a **new** temporary workspace using their existing
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
in this public repository. This prepares sources for the independent HQ Octopus project,
**not** permission to repoint the existing production bridge or deploy.

## Cross-repo PostgreSQL 16 + Ruby RAG contract (not yet attested)

The original monorepo's `apps/rag-ruby/test/migrated_schema_test.rb`
uses `../../api/src/dual_lineage/db/migrations`, which does not exist within
the separate HQ Workloads checkout. Never skip that test or silently substitute
SQLite. The verified overlay copies the small Ruby test source and links the
**exact pinned HQ Core migration directory** without modifying either Git tree:

```sh
python3 scripts/prepare-hq-rag-overlay.py \
  --manifest release-manifest.json \
  --workspace /tmp/ayahos-hq-candidate \
  --output /tmp/ayahos-hq-rag-overlay
```

On an explicitly **disposable, loopback-only PostgreSQL 16 + pgvector** Octopus
verification worker, install pinned Ruby dependencies one job at a time and
run **all** RAG tests against the Core v23 schema:

```sh
# Values below are illustrative TEST-ONLY local credentials, never production.
export TEST_DATABASE_URL='postgresql://ayahos_ci:octopus_ephemeral_test_only@127.0.0.1:5432/ayahos_ci'
export CI_TEST_DATABASE_IS_DISPOSABLE=1 RAG_REQUIRE_PGVECTOR=1
source scripts/ci/test_database_guard.sh
require_test_database rag
psql "$TEST_DATABASE_URL" -v ON_ERROR_STOP=1 -tAc \
  "SELECT count(*) FROM pg_extension WHERE extname='vector'" | grep -qx 1
cd /tmp/ayahos-hq-rag-overlay/apps/rag-ruby
bundle config set path vendor/bundle
bundle install --jobs 1 --retry 1
bundle exec rake test
```

Do not count the gate as passed if there are skipped schema/vector tests, if
the database is not disposable, or if Ruby cannot use the linked HQ Core SQL.
Set small PG shared buffers and serial native-gem installation on memory-bound
workers; investigate exit code 137, never waive it. The overlay evidence is
**candidate-only**, not a passing pgvector result.

For **Octopus Cloud**, use the existing separate `AyahOS HQ Verification`
project (`Projects-21`). Verify its GitHub App connection is scoped to the five approved
`ayahos-hq` repositories under Deploy > Manage > GitHub Connections. Octopus
GitHub connections can authenticate additional Git resources without a new PAT;
pin Git resources to the release manifest's immutable revisions. Keep the
existing `AyahOS` monorepo project and its Worker bridge unchanged. The HQ
project's existing three-step success is preliminary evidence only. Add and run
manifest-pinned five-repository verification on an authorized worker before
claiming full cross-repository acceptance.

See `MIGRATION-GATES.md` and master [migration issue #243](https://github.com/fuaadabdullah/AyahOS_Dual_Lineage/issues/243).
