#!/usr/bin/env python3
"""Stage exact Git revisions for a *candidate* HQ release, without running Octopus.

Requires existing authenticated GitHub CLI permissions for five repositories.
Never changes an existing directory, production service, remote secret or release state.
Runs the offline clean-tree verifier before atomically publishing the workspace.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("hq_source_preflight", HERE / "verify-release-manifest.py")
assert SPEC and SPEC.loader
_PREFLIGHT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(_PREFLIGHT)
verify = _PREFLIGHT.verify

REPOSITORIES = dict(_PREFLIGHT.REPOSITORIES)
SHA = re.compile(r"^[0-9a-f]{40}$")
CANONICAL = "fuaadabdullah/AyahOS_Dual_Lineage"
RULE = "platform_git_sha_is_an_ancestor_of_manifest_commit"
ACCEPTANCE = ("octopus_exact_sha", "database_restore_rehearsal",
              "authenticated_live_smoke", "rollback_rehearsal")


def refs(manifest: dict, platform_head: str) -> dict[str, str]:
    """Validate non-deployable source revisions without trusting mutable main refs."""
    if not isinstance(manifest, dict) or manifest.get("release_status") != "candidate":
        raise ValueError("only non-deployable candidates may be assembled")
    if manifest.get("schema_version") != 1:
        raise ValueError("invalid candidate schema")
    if manifest.get("source_authority") != CANONICAL:
        raise ValueError("unknown canonical source authority")
    if manifest.get("platform_manifest_commit_rule") != RULE:
        raise ValueError("unsupported platform manifest pinning rule")
    origin = manifest.get("source_commit")
    if not isinstance(origin, str) or not SHA.fullmatch(origin):
        raise ValueError("invalid immutable extraction source")
    if not isinstance(platform_head, str) or not SHA.fullmatch(platform_head):
        raise ValueError("explicit immutable --platform-head SHA required")
    components = manifest.get("components")
    if not isinstance(components, dict) or set(components) != set(REPOSITORIES):
        raise ValueError("unexpected component inventory")
    acceptance = manifest.get("acceptance", {})
    if not isinstance(acceptance, dict) or any(acceptance.get(k) != "pending" for k in ACCEPTANCE):
        raise ValueError("release acceptance cannot be attested by source assembly")
    compatibility = manifest.get("compatibility", {})
    if (not isinstance(compatibility, dict) or
        compatibility.get("artifact_contract_status") != "pending-independent-build" or
        compatibility.get("cross_repository_acceptance") != "pending"):
        raise ValueError("independent artifact and integration checks are required")
    selected = {}
    for name, repo in REPOSITORIES.items():
        entry = components[name]
        if not isinstance(entry, dict) or entry.get("repository") != repo:
            raise ValueError("component repository identity mismatch: " + name)
        sha = entry.get("git_sha")
        if not isinstance(sha, str) or not SHA.fullmatch(sha):
            raise ValueError("invalid immutable Git SHA: " + name)
        if entry.get("source_commit") != origin or entry.get("artifact_sha256") is not None:
            raise ValueError("candidate has unverified source or artifact data: " + name)
        selected[name] = platform_head if name == "ayahos-platform" else sha
    return selected


def clone_at(repository: str, sha: str, destination: Path) -> None:
    """Clone an allowlisted immutable source using GH CLI or configured Git.

    Git fallback is for Linux workers with a supported credential helper but no
    gh binary. Neither path embeds tokens, shells out through a shell, or
    accepts arbitrary repositories. An available-but-broken gh must fail closed.
    """
    if repository not in REPOSITORIES.values() or not SHA.fullmatch(sha):
        raise ValueError("unknown HQ repository or invalid immutable Git revision")
    environment = dict(os.environ, GH_PROMPT_DISABLED="1", GIT_TERMINAL_PROMPT="0")
    if shutil.which("gh"):
        clone_command = [
            "gh", "repo", "clone", repository, str(destination),
            "--", "--quiet", "--no-checkout",
        ]
    else:
        clone_command = [
            "git", "clone", "--quiet", "--no-checkout",
            "https://github.com/" + repository + ".git", str(destination),
        ]
    commands = (
        clone_command,
        ["git", "-C", str(destination), "checkout", "--detach", "--quiet", sha],
    )
    for cmd in commands:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False,
                                  timeout=180, env=environment)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            raise ValueError("Git/GitHub tooling missing or timed out while fetching " + repository) from None
        if proc.returncode != 0:
            # Suppress child stdout/stderr; credential helpers can emit secrets.
            raise ValueError("immutable HQ checkout failed for " + repository) from None


def assemble(manifest_path: Path, destination: Path, platform_head: str) -> Path:
    """Complete an isolated workspace or delete it entirely on any failure."""
    manifest_bytes = manifest_path.read_bytes()
    data = json.loads(manifest_bytes)
    revisions = refs(data, platform_head)
    verify(manifest_path, None)
    if destination.exists() or destination.is_symlink():
        raise ValueError("destination already exists; refusing overwrite")
    if not destination.parent.is_dir():
        raise ValueError("destination parent does not exist")
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        for name, revision in revisions.items():
            clone_at(REPOSITORIES[name], revision, staging / name)
        # The manifest used for the decision must be *identical* to the immutable
        # version in the checked-out platform commit, not a local mutable override.
        if (staging / "ayahos-platform" / "release-manifest.json").read_bytes() != manifest_bytes:
            raise ValueError("platform checkout manifest differs from requested candidate manifest")
        verify(manifest_path, staging)
        receipt = {
            "schema_version": 1,
            "cutover_ready": False,
            "candidate_release_id": data.get("release_id"),
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "platform_checkout_sha": platform_head,
            "component_checkout_shas": revisions,
            "artifact_digests": "pending-independent-build",
            "octopus_and_live_acceptance": "pending",
        }
        (staging / "CANDIDATE-SOURCE-EVIDENCE.json").write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
        )
        if destination.exists() or destination.is_symlink():
            raise ValueError("destination appeared during assembly")
        staging.rename(destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("release-manifest.json"))
    parser.add_argument("--workspace", type=Path, required=True,
                        help="new, non-existent target directory for immutable source")
    parser.add_argument("--platform-head", required=True,
                        help="full 40-char platform commit containing the manifest")
    args = parser.parse_args()
    try:
        result = assemble(args.manifest, args.workspace, args.platform_head)
    except (OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print("CANDIDATE ASSEMBLY BLOCKED: " + str(exc), file=sys.stderr)
        return 1
    print("Verified immutable, clean candidate sources at " + str(result))
    print("Not a deployment or Octopus acceptance. Artifacts, integration and rollback remain pending.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
