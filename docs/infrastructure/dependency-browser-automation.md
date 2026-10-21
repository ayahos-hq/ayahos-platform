# Reviewed dependency updates and deployed-browser smoke

## Renovate (configured, not yet installed)

The root `renovate.json` schedules a small batch of updates on Monday mornings
in America/New_York. No PR is auto-merged. Major updates require an explicit
Dependency Dashboard approval. Review the lockfile, test impact and the
Octopus gates before merging changes. Repository configuration alone does
**not** install the Renovate GitHub App; an authorized repository administrator
must enable it for this private repository.

Do not create GitHub Actions workflows for Renovate or use an unaudited
review bot with live credentials. Overmind can propose updates, but merging
and privileged deployment remain behind the existing Undermind/GitHub gates.

## Playwright public-site browser smoke (available, not CI-triggered)

Install in an isolated Python environment (not in the runtime image):

```sh
python -m pip install -r scripts/ci/requirements-browser.txt
python -m playwright install chromium
LIVE_PUBLIC_SITE_URL=https://ayahos.pages.dev \
  EXPECTED_SHA=<full-main-commit-sha> \
  ruby scripts/ci/public_site_browser_smoke.py
```

The script fails unless `/api/build` attests the exact 40-character expected
SHA on `main`. It then loads the real deployed UI in headless Chromium,
checks the composer, intercepts `/api/chat`, and confirms the returned
fixture is rendered. The browser session is isolated, disables the consent
checkbox, and **does not** send a live model request or test live provider
routing. It reports a one-line structured PASS/FAIL record.

A **real** API/proxy/inference smoke is separate:
`ruby scripts/public_chat_smoke.rb`; it may consume provider quota and
requires deployment-safe rate limits. Full live release tests also require
the existing secret-scoped operators and provenance gates.

Next integration step: attach the browser command to a *post-deploy*
Octopus verification task after the destination's SHA converges, with
a non-production preview test first. Do **not** run it as a gate against an
unrelated or stale production URL, and do not treat a committed Octopus OCL
process as proof it ran. Octopus runtime logs/status and branch protection
must be checked before declaring it active.

## Retired status publishers

GitHub still reported CircleCI and Vercel failure/pending statuses on
`main` at `92346341b9560f2b9283e7508d44a7195c708408` as of
2026-10-20. Removing CI YAML does not revoke CircleCI's GitHub webhook/App,
remove Vercel's old Git integration, or change branch protection. An
administrator must disable their stale GitHub integration/status publishers
and replace any required-check names with verified Octopus status checks.
Do not waive required checks or mistake removal of a check for a passing run.
