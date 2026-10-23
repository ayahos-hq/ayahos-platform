#!/usr/bin/env python3
"""Verify the immutable five-repository release manifest.

This is an offline shape and identity check. It never treats missing artifact
digests or pending live gates as a releasable result.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

SHA = re.compile(r"\A[0-9a-f]{40}\Z")
ARTIFACT = re.compile(r"\A[0-9a-f]{64}\Z")
REPOSITORIES = {
    "ayahos-site": "ayahos-hq/ayahos-site",
    "ayahos-core": "ayahos-hq/ayahos-core",
    "ayahos-admin": "ayahos-hq/ayahos-admin",
    "ayahos-platform": "ayahos-hq/ayahos-platform",
    "ayahos-workloads": "ayahos-hq/ayahos-workloads",
}


def git_head(path: Path) -> str:
    # Prefer the fetched release ref. The shared workspace may intentionally
    # have an older working branch with unrelated changes.
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "origin/main"], text=True
        ).strip()
    except subprocess.CalledProcessError:
        pass
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
    ).strip()


def is_ancestor(path: Path, ancestor: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(path), "merge-base", "--is-ancestor", ancestor, "origin/main"],
        check=False,
    ).returncode == 0


def verify(path: Path, workspace_root: Path | None) -> None:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported manifest schema")
    if manifest.get("release_status") != "candidate":
        raise ValueError("only candidate manifests may be verified offline")
    if not SHA.fullmatch(manifest.get("source_commit", "")):
        raise ValueError("invalid canonical source commit")

    components = manifest.get("components")
    if not isinstance(components, dict) or set(components) != set(REPOSITORIES):
        raise ValueError("manifest must contain exactly the five HQ repositories")
    for name, repository in REPOSITORIES.items():
        component = components[name]
        if component.get("repository") != repository:
            raise ValueError(f"wrong repository identity for {name}")
        for field in ("git_sha", "source_commit"):
            if not SHA.fullmatch(component.get(field, "")):
                raise ValueError(f"invalid {field} for {name}")
        if component["source_commit"] != manifest["source_commit"]:
            raise ValueError(f"source commit drift for {name}")
        digest = component.get("artifact_sha256")
        if digest is not None and not ARTIFACT.fullmatch(digest):
            raise ValueError(f"invalid artifact digest for {name}")
        if workspace_root is not None and name == "ayahos-platform":
            if not is_ancestor(workspace_root / name, component["git_sha"]):
                raise ValueError("platform source SHA is not an ancestor of origin/main")
        elif workspace_root is not None:
            checkout = workspace_root / name
            if git_head(checkout) != component["git_sha"]:
                raise ValueError(f"local checkout HEAD differs for {name}")

    compatibility = manifest.get("compatibility", {})
    if compatibility.get("api_contract") != "python-authority-ruby-boundary-v1":
        raise ValueError("unexpected API contract declaration")
    if compatibility.get("database_schema") != 22:
        raise ValueError("unexpected database schema declaration")
    if compatibility.get("artifact_contract_status") != "pending-independent-build":
        raise ValueError("artifact status must remain fail-closed until built")
    if compatibility.get("cross_repository_acceptance") != "pending":
        raise ValueError("cross-repository acceptance must remain pending")

    acceptance = manifest.get("acceptance", {})
    required = ("octopus_exact_sha", "database_restore_rehearsal",
                "authenticated_live_smoke", "rollback_rehearsal")
    if any(acceptance.get(key) != "pending" for key in required):
        raise ValueError("offline manifest cannot attest live acceptance")
    print("Verified candidate manifest: five exact repository SHAs, one source commit, "
          "contract/schema declarations, and fail-closed pending gates.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="release-manifest.json", type=Path)
    parser.add_argument("--workspace-root", type=Path,
                        help="also compare fetched origin/main sibling repository refs")
    args = parser.parse_args()
    try:
        verify(args.manifest, args.workspace_root)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"RELEASE MANIFEST CHECK FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
