# HQ verification bridge: what `octopus/hq-operator-verified` actually attests

Status: owner decision recorded 2026-11-22. This note is the durable record;
it deliberately lives outside the attested extraction tree (deploy/,
scripts/, .octopus/, docs/infrastructure/), whose files are pinned
byte-for-byte to the monorepo snapshot in SOURCE-PROVENANCE.json and must
not be edited.

## Decision

The commit status `octopus/hq-operator-verified`, posted by the
`ayahos-hq-verification-bridge` Worker after an Octopus release, is
**candidate-scoped**. It attests the five-repository AyahOS HQ release
candidate and the Octopus release machinery that evaluated it. It does
**not** attest the source integrity of the individual platform pull
request head it is posted on.

PR-head source integrity for this repository is gated by the GitHub
Actions check `verify` (workflow `platform-isolation.yml`), which is the
required status context in branch protection for `main` — strict, with
linear history and conversation resolution, `enforce_admins` on.
`octopus/hq-operator-verified` is **not** a required context and must not
be treated as a merge gate or as a substitute for `verify`.

## Evidence (2026-11-21, exercised end to end for issue #47)

Passing case — platform PR #72 (bridge cron record):

- PR heads `0ec92d3` and `b602667`, and the merge commit `36506e2` on
  `main`, all carry `octopus/hq-operator-verified` = success
  ("All required Octopus gates passed"; Octopus ServerTasks-16357,
  ServerTasks-16360, ServerTasks-16361).
- GitHub `verify` and Cloudflare Workers Builds also passed on the
  merged head.

Failure case — probe PR #73 (closed unmerged, branch deleted), which
added one junk file under `deploy/`, breaking the SOURCE-PROVENANCE
file-set check, on head `07e13b8`:

- GitHub `verify`: **failure** — correct.
- Workers Builds `ayahos-hq-verification-bridge`: **failure** — correct.
- Merge: **blocked** — correct; the binding gate held.
- `octopus/hq-operator-verified`: **success** (ServerTasks-16376) — the
  Octopus lane did not catch the broken platform source at the exact
  commit, because platform source verification at the exact commit is
  not one of its lanes.

## Alternatives considered

- (a) Add platform source verification at the exact commit (for example
  `scripts/verify-platform.py` against the PR head) to the Octopus
  lanes, so the Octopus status would also attest PR-head integrity.
  Not adopted: it duplicates the existing required `verify` gate.
- (b) Document the Octopus status as candidate-scoped and rely on
  GitHub `verify` for PR-head integrity. **Adopted by the owner
  2026-11-22.**

## Revisit condition

If `octopus/hq-operator-verified` is ever proposed as a required branch
protection context, or as a gate for anything beyond this repository's
release-candidate flow, option (a) must be implemented first, so the
status attests the exact commit it is posted on. Until then, a green
Octopus status on a commit means only: the HQ release candidate and
machinery evaluated by Octopus passed.
