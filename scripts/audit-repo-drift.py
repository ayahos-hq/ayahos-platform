#!/usr/bin/env python3
"""Read-only three-way AyahOS drift audit against an immutable extraction base.

Requires an explicit operator 'gh' login or HQ_READ_TOKEN with read-only\naccess to the six repositories. Compares Git blob SHAs,
never retrieves source contents or prints credentials. Not deployment approval.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request

SOURCE = "fuaadabdullah/AyahOS_Dual_Lineage"
PREFIXES = {
    "ayahos-site": ("apps/site/", "packages/shared/"),
    "ayahos-core": ("apps/api/", "docs/architecture/", "Dockerfile", "Makefile", ".dockerignore"),
    "ayahos-admin": ("apps/web/", "packages/shared/"),
    "ayahos-platform": (".octopus/", "deploy/", "scripts/ci/", "scripts/db/", "docs/infrastructure/"),
    "ayahos-workloads": (
        "apps/rag-ruby/", "apps/ruby_worker/", "apps/control-ruby/",
        "apps/sandbox_worker/", "models/", "benchmarks/", "experiments/",
        "ml-requirements.txt",
    ),
}
SHA = re.compile(r"^[a-f0-9]{40}$")


def owned(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path.startswith(prefix) if prefix.endswith("/") else path == prefix
               for prefix in prefixes)


def classify(base: str | None, monorepo: str | None, target: str | None) -> str:
    if monorepo == target:
        return "synced"
    if monorepo == base:
        return "hq_only"
    if target == base:
        return "monorepo_only"
    return "both_diverged"


def diff(base: dict[str, str], monorepo: dict[str, str], target: dict[str, str],
         prefixes: tuple[str, ...]) -> list[dict[str, str | None]]:
    paths = sorted(set(base) | set(monorepo) | set(target))
    found = []
    for path in paths:
        if not owned(path, prefixes):
            continue
        before, current, hq = base.get(path), monorepo.get(path), target.get(path)
        kind = classify(before, current, hq)
        if kind != "synced":
            found.append({"path": path, "kind": kind, "baseline": before,
                          "monorepo": current, "hq": hq})
    return found


class GitHubReader:
    def __init__(self, token: str, *, auth: str = "token"):
        if auth not in ("token", "gh"):
            raise ValueError("Unsupported GitHub audit authentication mode")
        if auth == "token" and not token:
            raise ValueError("HQ_READ_TOKEN or GITHUB_TOKEN is required for private repositories")
        self._auth = auth
        self._token = token

    def get(self, endpoint: str) -> dict:
        if self._auth == "gh":
            try:
                completed = subprocess.run(
                    ["gh", "api", "repos/" + endpoint],
                    capture_output=True, text=True, check=False, timeout=20,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                raise ValueError("GitHub CLI is unavailable or timed out") from None
            if completed.returncode:
                # Never relay CLI stderr, which may contain account or API details.
                raise ValueError("GitHub CLI read failed; check gh login and repository access")
            try:
                return json.loads(completed.stdout)
            except json.JSONDecodeError:
                raise ValueError("GitHub CLI returned invalid JSON") from None
        request = urllib.request.Request(
            "https://api.github.com/repos/" + endpoint,
            headers={"Authorization": "Bearer " + self._token,
                     "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28",
                     "User-Agent": "ayahos-readonly-drift-audit"},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise ValueError(f"GitHub read failed: HTTP {exc.code} for {endpoint.split('?')[0]}") from None
        except urllib.error.URLError:
            raise ValueError("GitHub read failed: network unavailable") from None

    def head(self, repository: str) -> str:
        sha = self.get(f"{repository}/git/ref/heads/main")["object"]["sha"]
        if not SHA.fullmatch(sha):
            raise ValueError(f"Invalid default-branch SHA: {repository}")
        return sha

    def tree(self, repository: str, commit_sha: str) -> dict[str, str]:
        if not SHA.fullmatch(commit_sha):
            raise ValueError(f"Invalid tree ref for {repository}")
        data = self.get(f"{repository}/git/trees/{commit_sha}?recursive=1")
        if data.get("truncated") or not isinstance(data.get("tree"), list):
            raise ValueError(f"Incomplete Git tree for {repository}; cannot attest drift")
        return {entry["path"]: entry["sha"] for entry in data["tree"]
                if entry.get("type") == "blob"}


def audit(reader: GitHubReader, manifest: dict) -> dict:
    baseline_sha = manifest["source_commit"]
    if not SHA.fullmatch(baseline_sha):
        raise ValueError("Invalid immutable extraction baseline")
    if set(manifest["components"]) != set(PREFIXES):
        raise ValueError("Incomplete five-component release manifest")
    monorepo_sha = reader.head(SOURCE)
    baseline = reader.tree(SOURCE, baseline_sha)
    current = reader.tree(SOURCE, monorepo_sha)
    report: dict = {
        "schema_version": 1, "baseline": baseline_sha,
        "monorepo": {"repository": SOURCE, "sha": monorepo_sha},
        "cutover_ready": False, "components": {},
    }
    for name, prefixes in PREFIXES.items():
        repository = "ayahos-hq/" + name
        component = manifest["components"][name]
        if component.get("repository") != repository:
            raise ValueError(f"Wrong repository mapping: {name}")
        pinned = component.get("git_sha")
        if not isinstance(pinned, str) or not SHA.fullmatch(pinned):
            raise ValueError(f"Missing or invalid manifest SHA: {name}")
        head = reader.head(repository)
        target = reader.tree(repository, head)
        changes = diff(baseline, current, target, prefixes)
        counts = {kind: sum(entry["kind"] == kind for entry in changes)
                  for kind in ("monorepo_only", "hq_only", "both_diverged")}
        report["components"][name] = {
            "repository": repository, "head_sha": head, "manifest_sha": pinned,
            "head_matches_manifest": head == pinned,
            "changed_paths": len(changes), "counts": counts, "files": changes,
        }
    # Even zero source drift cannot certify the missing artifact, Octopus,
    # authenticated chat, database recovery and rollback acceptance gates.
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("release-manifest.json"))
    parser.add_argument("--output", type=Path, help="write reproducible JSON evidence")
    parser.add_argument("--enforce", action="store_true", help="nonzero exit if components diverge")
    parser.add_argument("--auth", choices=("token", "gh"), default="token",
                        help="explicit operator gh login or a scoped injected read token")
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        reader = GitHubReader(os.getenv("HQ_READ_TOKEN") or os.getenv("GITHUB_TOKEN") or "",
                              auth=args.auth)
        report = audit(reader, manifest)
        if args.output:
            args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        for name, entry in report["components"].items():
            print(f"{name}: {entry['changed_paths']} drift paths "
                  f"{entry['counts']} manifest_head_match={entry['head_matches_manifest']}")
        if args.enforce and any(item["changed_paths"] or
                                (name != "ayahos-platform" and not item["head_matches_manifest"])
                                for name, item in report["components"].items()):
            print("DRIFT GATE: BLOCKED (no service cutover)", file=sys.stderr)
            return 2
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"DRIFT AUDIT: FAILED CLOSED ({exc})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
