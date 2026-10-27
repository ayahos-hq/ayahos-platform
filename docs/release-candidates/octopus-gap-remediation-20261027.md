# Octopus gap remediation checkpoint — 2026-10-27

This is an append-only task record. Findings are read-only live observations;
the code changes in this branch have not been pushed or deployed.

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
