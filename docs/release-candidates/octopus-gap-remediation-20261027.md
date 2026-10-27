# Octopus gap remediation checkpoint — 2026-10-27

This is an append-only task record. Findings and action states below describe
their recorded point in time. Later checkpoints supersede earlier pending states
explicitly; read the latest checkpoint for the current publication status.

## Observations

1. Native Octopus CLI authentication succeeds against `https://ayahos.octopus.app`.
   The enrolled diagnostic helper explicitly calls for a read-only credential.
   Do not copy that credential into a writable Cloudflare bridge integration.
2. `Projects-21` is the isolated **AyahOS HQ Verification** project. Latest HQ
   release `Releases-532` (`0.0.18`), deployment `Deployments-351`, task
   `ServerTasks-1944`, succeeded on 2026-10-24. It ran manifest shape validation,
   56 offline tests and Core source attestation. Only Platform and Core were
   acquired. This corrects the older assumption that HQ had no successful run.
3. That release selected Platform `f01dcced85ea294bdcdacbebb0730dc6819aaa1d`
   and Core `ce43a6c99b2f80bc6f0b4903687373e2d007daff`. Current Platform main
   is `094328e66a90c7d4f629db8c31e1b1d0c7bca246`. Site, Admin and Workloads
   have no source steps in the release's immutable process snapshot.
4. Current Platform branch protection requires `octopus/hq-operator-verified`.
   The older Platform commit has a success under that context. Current main
   has no commit status. Never transfer the older success onto a new SHA.
5. Monorepo AyahOS is a separate project. Recent monorepo tasks include success
   (`ServerTasks-3482`) and a later API/PostgreSQL failure (`ServerTasks-3485`).
   Their results are not HQ acceptance and do not justify repointing its bridge.

## Local remediation

- GitHub workflow now triggers for the Octopus wrapper, offline runner, all
  root script tests and the `tests/` suite; it runs the same complete offline
  runner as Octopus. Shell syntax checking includes `scripts/octopus/` and
  propagates syntax failures.
- The manifest wrapper supports `HQ_MANIFEST_PYTHON` for an explicit local
  interpreter; Ubuntu keeps `python3` as its default. Windows shell regression
  tests explicitly use Git Bash and enable native path conversion.
- `scripts/audit-octopus-release.py` uses only CLI GET requests and validates
  release → immutable process → deployment → task → successful step evidence.
  It compares all five source revisions, rejects partial/stale/disabled/skipped
  evidence, suppresses child errors, and never posts GitHub statuses. Even full
  source coverage keeps `production_accepted: false`.
- `octopus-source-coverage-20261027.json` records the rejected current-main
  comparison for the existing release. Exit 1 is an expected incomplete gate;
  exit 2 means invalid evidence or a tool/request failure.
- Five clean, immutable candidate repositories were assembled locally with
  `assemble-hq-workspace.py` at the current Platform SHA. The receipt is in
  `C:/Users/Admin/ayahos-hq/_worktrees/octopus-candidate-sources-20261027/`.
  This establishes local source availability, not hosted Octopus integration.

## Remaining live changes and acceptance

The next proposed external step is to push this isolated branch for review,
then run the isolated HQ Development verification on its reviewed immutable
commit after merge. No production host, DNS, monorepo bridge or secret change
is included in that step. A rerun of the existing three-step process will prove
only those three steps; it cannot close the five-component acceptance gap.

Follow-up implementation must wire clean manifest-pinned five-repository
assembly on an authorized worker, preserve the eight required integration
lanes, and capture exact task outcomes and independent artifact digests.
PostgreSQL/pgvector, isolated restore, authenticated smoke and rollback remain
separate pending gates. Do not mark tracking issues #6 or #35 complete from
this patch or a three-step green task. Any worker/secret/bridge change needs
reviewed configuration, appropriate scoped credentials and confirmed intent.

## Validation record

- Eight adversarial audit tests passed locally.
- The audit executed against the live Octopus release and correctly rejected
  stale Platform plus absent Site/Admin/Workloads source coverage.
- Five-repository candidate source assembly succeeded locally.
- All 26 offline Node bridge tests passed.
- Immutable platform provenance and offline candidate manifest checks passed.
- Native Windows full suite encountered pre-existing symlink privilege errors
  and eight Linux-only skips. Shell invocation failures were corrected in this
  branch. A disposable Linux copy is used for the complete suite.
- Gemini independent review was attempted in the isolated checkout but its
  provider requests failed; no independent review result is claimed.

Live acceptance, hosted CI and production deployment remain unverified for
this branch. Record later results below rather than replacing these findings.

### Subsequent local results

- The first disposable Linux copy retained Windows CRLF shell endings and
  failed before script logic. This was a copy-format issue. The next disposable
  copy used LF shell endings, matching a Linux Git checkout: **53 script tests
  and 11 tests-directory tests passed, with no skips** (64 total).
- The four Windows shell-wrapper regression tests passed using Git Bash and
  the explicit Python interpreter, with MSYS native path conversion enabled.
- No hosted CI run, branch push, live process update or fresh Octopus execution
  was performed by this task.

## Publication and hosted results: 2026-10-27

After explicit user approval, branch `codex/octopus-gaps-20261027` was pushed and
[draft PR #42](https://github.com/ayahos-hq/ayahos-platform/pull/42) opened with
implementation commit `1b660ff7fb2a50e22c28d996c78e86ada985f7d0`. This supersedes
the earlier unpushed/local-only publication state; it does not change the earlier
test observations or constitute live deployment authorization.

[GitHub run 40465404016](https://github.com/ayahos-hq/ayahos-platform/actions/runs/40465404016)
completed successfully for that exact implementation commit. Its source and
manifest checks, complete offline suites, shell syntax and mocked bridge tests
passed. These are **hosted offline CI results**, distinct from Octopus acceptance.

The separate provider check `Workers Builds: ayahos-hq-verification-bridge`
completed with **failure**. The observed check links to
[Cloudflare build c4f0fbbc-b4fc-4a59-94b7-e1c2ba62c8dd](https://dash.cloudflare.com/265071fc5a2ac8bbe85e2bd724361080/workers/services/view/ayahos-hq-verification-bridge/production/builds/c4f0fbbc-b4fc-4a59-94b7-e1c2ba62c8dd).
No root cause or successful Worker deployment is established. The PR is not fully
green. This task did not explicitly invoke a deployment or change live settings;
the provider check appeared following publication.

No commit status was observed for `1b660ff` under the protected Octopus context
`octopus/hq-operator-verified`. A fresh exact-commit HQ Octopus verification,
five-component source/integration coverage, artifact digests, PostgreSQL/pgvector,
restore, authenticated smoke and rollback remain pending. No merge or Octopus
execution was performed.

The README and migration gates now link this checkpoint, document the existing
HQ project and required status context, and distinguish the passing GitHub run
from the failed Cloudflare check. Historical imported infrastructure/bridge docs
remain immutable source snapshots; current HQ operating corrections belong in
the root docs and this task record. Machine-readable candidate acceptance and
the original source-audit JSON remain unchanged because no new acceptance or
source audit has occurred. Later documentation commits do not inherit the named
implementation commit's CI result.

## Follow-up diagnosis and integration proof: 2026-10-27

- Documentation commit `4995f0df38dcbc7ca868636489f92de5363ba92d` passed hosted
  [GitHub verification run 40465739482](https://github.com/ayahos-hq/ayahos-platform/actions/runs/40465739482).
  Logs confirm 53 script tests, 11 tests-directory tests, and 26 mocked bridge
  tests passed. This supersedes the earlier pending-check state for that commit.
- The same commit's separate Cloudflare check failed, build
  `89b3c151-13c0-4162-8d48-2701200382a2`. The dashboard tab opened for diagnosis
  reached Cloudflare sign-in; the current Edge browser session is unauthenticated.
- Warden doctor confirmed native Cloudflare CLI authentication. Using that
  existing session for GET requests returned HTTP **403** for both the HQ Worker
  trigger endpoint and this build's log endpoint. No credential was displayed,
  stored or transferred into another integration. Authentication and Builds API
  authorization are distinct; this is not a general Cloudflare login failure.
- Existing [PR #38](https://github.com/ayahos-hq/ayahos-platform/pull/38), commit
  `84337c9bb78a36af8087faaf8ac31bd7ae6bca7c`, already contains the isolated HQ
  Worker config, exact-SHA build guard and build-command runbook. Its prior notes
  describe wrong checkout/root settings and the same Builds API permission gap.
  Those notes inform the diagnosis; the current failure's raw build log remains
  inaccessible, so that precise root cause is not re-proven here.
- PR #38 and documentation commit `4995f0d` combine without merge conflicts into
  temporary tree `5fd4bd9879c24da74811e9bfb64b4fbee435a5e5`. A disposable Linux
  extraction of this tree passed immutable platform provenance (69 blobs),
  candidate manifest validation and **80 offline tests without skips** (69 script
  tests plus 11 tests-directory tests). An initial Windows-converted archive
  failed on CRLF shell endings; re-export with `core.autocrlf=false` matched a
  Linux checkout and passed. This is local integration evidence only.
- Neither PR branch was merged or rewritten for that integration test. No
  Cloudflare build was manually retried and no trigger, credential, Worker
  deployment, Octopus process or permission was changed.

Next action: after the operator signs into the open Cloudflare dashboard, read
the failing build log and exact trigger settings, reconcile them against PR #38's
runbook, and prepare the smallest reviewed correction. Do not blind-copy the
monorepo config or bypass the red check. Applying a live correction or deploying
a preview remains a separate Action Gateway step with explicit intent.

## Authorized HQ build repair: 2026-10-27

The user requested protection of `Fly_API_TOKEN`, Cloudflare sign-in, and then
explicitly said "Fix it" after the build failure was identified. The token's
existing project variable was changed to `Type: Sensitive`, `IsSensitive: true`
via the authenticated Octopus API. Live read-back confirmed the original scope
was preserved, the value was not returned, and variable-set version became 3.
No token value is included in this record.

Cloudflare sign-in succeeded through the existing GitHub browser session.
Authenticated build `89b3c151-13c0-4162-8d48-2701200382a2` confirmed all three
failure causes: its build command switched to
`feat/pinned-hq-artifact-assembly-20261025`, its root was
`/deploy/octopus-github-bridge`, and Wrangler rejected the selected configuration
because `previews` was missing. This supersedes the earlier inability to read
the dashboard and the prior unproven-root-cause qualification. Native OAuth
Builds API authorization remains distinct from working browser access.

Only six files were integrated verbatim from PR #38 commit
`84337c9bb78a36af8087faaf8ac31bd7ae6bca7c`: the HQ config/runbook, exact-SHA
guard/test and provenance/verifier updates. Unrelated access-doctor changes
were excluded. The resulting candidate passed 69 offline tests (58 script plus
11 tests-directory), 26 mocked bridge tests, provenance/manifest checks and
Wrangler 4.152.0 dry-run packaging. Provenance now audits 69 entries: the
existing 66 plus three HQ verification files.

The production active version before changes was `2716f1a7` at 100% traffic.
The authenticated settings showed production TASKS namespace
`49ce086dc87f4de9a5110e5771907cb3`; the reviewed preview config selects separate
namespace `2b5af79207114dec9989bc1d952c3c9d`. No production secrets or cron are
declared in that preview configuration. Preview URLs are public, and their
missing-credentials health response must not be misreported as an integration
success. Builds do not invoke Octopus acceptance or change runtime authority.

The reviewed dashboard changes replace the checkout command with exact-SHA
validation, use repository root `/`, pin the isolated HQ preview command and
replace the production upload command with `wrangler deploy --dry-run`.
Hosted execution and saved-setting/production read-back results follow below.

### Saved settings, retained preview override, and successful hosted retry

Production and Previews Base commands/root were saved and reloaded successfully.
The Preview Base runtime settings contained no secrets or bindings. The dashboard
KV list independently confirmed `ayahos-hq-verification-preview-tasks` at
`2b5af79207114dec9989bc1d952c3c9d`, separate from production TASKS.

Implementation commit `517e3eb97fdd100182bb38fdea7771e7d90f23bb` was pushed and
passed hosted GitHub run `40470736902`. Its first Cloudflare build
`9185800f-c8a0-4ec5-8daf-d8892d1af2a4` still executed the old checkout/root
commands. This corrects the initial assumption that Production/Previews Base
read-back proved the active branch trigger was repaired. Existing previews keep
independent build commands.

The environment selector exposed the existing `codex/octopus-gaps-20261027`
preview. Its own Settings > Builds still held the wrong branch checkout,
unqualified preview command and monorepo root. Those three fields were corrected
to the reviewed values, saved, and independently reloaded before retry.

The exact same commit was retried once. Cloudflare build
`aed5b502-e18f-4da7-8b99-dff035c5dc0b` succeeded, emitted
`HQ_WORKER_SOURCE_VERIFIED=517e3eb97fdd100182bb38fdea7771e7d90f23bb`, checked all
69 provenance entries and the candidate manifest, passed 26 mocked bridge tests,
and deployed the isolated preview with Wrangler 4.152.0. GitHub reports both
`verify` and `Workers Builds: ayahos-hq-verification-bridge` successful for that
implementation commit. The red check was repaired, not waived or replaced.

Production read-back after that successful build still showed version `2716f1a7`
at 100% traffic. Browser health returned `ok` for production and reported missing
`GITHUB_WEBHOOK_SECRET` / `OCTOPUS_API_KEY` for the preview. Native Python HTTP
probes returned 403 at the edge for both URLs, so browser responses are the
application evidence; no unsupported HTTP status claim is made from them.

PR #42 title/body were rewritten around the final source/build repair. It
remains a draft. No main merge, production Worker release, new permission,
secret copy, monorepo bridge change or Octopus release occurred. The broader
exact-SHA five-component/eight-lane, artifact, database, smoke and rollback gates
remain pending. Later documentation revisions require their own hosted checks.
