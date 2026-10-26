#!/usr/bin/env python3
"""Read-only, credential-safe preflight for AyahOS HQ developer access.

Does not retrieve, display, alter, persist, refresh, or mint secrets. Results
are CLI reachability evidence, not production authority or CI acceptance.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import re
import shutil
import subprocess
from typing import Callable

ACCOUNT_ID = re.compile(r"\b[a-f0-9]{32}\b", flags=re.I)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class Check:
    service: str
    status: str
    message: str
    action: str


Runner = Callable[[list[str]], CommandResult]


def safe_run(args: list[str]) -> CommandResult:
    """Subprocess without a shell; stderr/stdout stay private to checks."""
    if shutil.which(args[0]) is None:
        return CommandResult(127)
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=25,
                              shell=False, encoding="utf-8", errors="replace",
                              check=False)
        return CommandResult(proc.returncode, proc.stdout, proc.stderr)
    except (OSError, subprocess.TimeoutExpired):
        return CommandResult(124)


def check_github(run: Runner = safe_run) -> Check:
    identity = run(["gh", "api", "user", "--jq", ".login"])
    if identity.returncode:
        return Check("github", "not_authenticated", "GitHub API session unavailable.",
                     "Use gh auth login as fuaadabdullah; never paste tokens into chat.")
    if identity.stdout.strip().lower() != "fuaadabdullah":
        return Check("github", "wrong_account", "Active GitHub identity differs from approved principal.",
                     "Select the existing fuaadabdullah gh account, without changing permissions.")
    access = run(["gh", "api", "repos/ayahos-hq/ayahos-platform", "--jq", ".full_name"])
    if access.returncode or access.stdout.strip().lower() != "ayahos-hq/ayahos-platform":
        return Check("github", "missing_access", "HQ platform repository read access not verified.",
                     "Check organization GitHub App permissions; avoid broad new PATs.")
    return Check("github", "ready", "Approved GitHub principal and HQ read access verified.",
                 "Writes/merges require separate repository gates.")


def check_cloudflare(run: Runner = safe_run, expected_account: str | None = None) -> Check:
    output = run(["wrangler", "whoami", "--profile", "ayahos-hq"])
    if output.returncode:
        return Check("cloudflare_hq", "not_authenticated", "Dedicated HQ Wrangler profile unavailable.",
                     "Owner signs in once with wrangler auth create ayahos-hq on the authorized desktop.")
    if not expected_account:
        return Check("cloudflare_hq", "needs_target", "Authenticated account cannot be validated without HQ account ID.",
                     "Pass --cloudflare-account-id from the owning account's dashboard.")
    if not ACCOUNT_ID.fullmatch(expected_account):
        return Check("cloudflare_hq", "invalid_target", "Expected HQ Cloudflare account ID is invalid.",
                     "Provide the exact account ID, not a zone/worker ID.")
    accounts = set(ACCOUNT_ID.findall(output.stdout))
    if expected_account.lower() not in {a.lower() for a in accounts}:
        return Check("cloudflare_hq", "wrong_account", "CLI identity cannot enumerate the HQ Worker account.",
                     "Owner grants this principal scoped membership to HQ, then re-authenticates the named profile.")
    return Check("cloudflare_hq", "ready", "Named Wrangler profile can enumerate HQ account.",
                 "Check service-level read/write permissions independently before any mutation.")


def check_octopus(run: Runner = safe_run) -> Check:
    result = run(["octopus", "space", "list", "--output-format", "json", "--no-prompt"])
    if result.returncode or "to get started with the octopus cli" in result.stdout.lower():
        return Check("octopus", "not_authenticated", "Octopus CLI session unavailable.",
                     "Owner uses octopus login for https://ayahos.octopus.app with read-scoped TaskView.")
    try:
        document = json.loads(result.stdout)
    except (ValueError, TypeError):
        return Check("octopus", "not_verified", "Octopus output is not an authenticated JSON result.",
                     "Verify CLI login and server locally without printing tokens.")
    spaces = (document.get("Spaces") or document.get("Items") or
              document.get("items") or document.get("spaces")) if isinstance(document, dict) else document
    if not isinstance(spaces, list) or not any(
        isinstance(space, dict) and space.get("Id", space.get("id")) == "Spaces-1"
        for space in spaces
    ):
        return Check("octopus", "missing_access", "Expected Octopus space was not verified.",
                     "Review exact tenant, space and TaskView scope.")
    return Check("octopus", "ready_read_only", "Octopus CLI can read the expected space.",
                 "Check project/task permissions before treating any CI release as accepted.")


def assess(expected_cloudflare: str | None, run: Runner = safe_run) -> list[Check]:
    return [check_github(run), check_cloudflare(run, expected_cloudflare), check_octopus(run)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cloudflare-account-id", help="Expected HQ account ID, never an API token")
    parser.add_argument("--json", action="store_true", help="Print sanitized statuses")
    args = parser.parse_args()
    if args.cloudflare_account_id and not ACCOUNT_ID.fullmatch(args.cloudflare_account_id):
        parser.error("Cloudflare account ID must be 32 hexadecimal characters")
    checks = assess(args.cloudflare_account_id)
    if args.json:
        print(json.dumps({"schema_version": 1, "checks": [asdict(c) for c in checks]}, indent=2))
    else:
        for check in checks:
            print(f"{check.service}: {check.status} - {check.message}\n  Next: {check.action}")
    return 0 if all(check.status in ("ready", "ready_read_only") for check in checks) else 2


if __name__ == "__main__":
    raise SystemExit(main())
