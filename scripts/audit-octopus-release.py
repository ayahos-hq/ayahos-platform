#!/usr/bin/env python3
"""Read-only HQ release source coverage audit; never posts a success status.

Uses the existing Octopus CLI session. Child output is captured, never echoed:
only allowlisted identities and audit findings appear in the report.
Exit 0 means five-repository source coverage, not production acceptance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

SHA = re.compile(r"[0-9a-f]{40}\Z")
PROJECT = "Projects-21"
SPACE = "Spaces-1"
REPOS = {"ayahos-" + name for name in ("platform", "core", "site", "admin", "workloads")}


def api(path: str) -> dict:
    try:
        result = subprocess.run(["octopus", "api", path, "--no-prompt"],
                                capture_output=True, text=True, timeout=60, check=False)
        if result.returncode:
            raise ValueError("Octopus read-only request failed")
        data = json.loads(result.stdout)
        if not isinstance(data, dict):
            raise ValueError("unexpected Octopus response")
        return data
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        raise ValueError("Octopus read-only request unavailable or invalid") from None


def audit(manifest: dict, platform_sha: str, release: dict, process: dict,
          task: dict, deployment: dict, details: dict) -> dict:
    if not SHA.fullmatch(platform_sha):
        raise ValueError("explicit immutable platform SHA required")
    components = manifest.get("components", {})
    if set(components) != REPOS:
        raise ValueError("manifest must identify all five HQ repositories")
    expected = {}
    for name in sorted(REPOS):
        component = components[name]
        if component.get("repository") != "ayahos-hq/" + name:
            raise ValueError("unexpected manifest repository identity")
        sha = platform_sha if name == "ayahos-platform" else component.get("git_sha")
        if not isinstance(sha, str) or not SHA.fullmatch(sha):
            raise ValueError("invalid manifest source revision")
        expected[name] = sha
    if (release.get("ProjectId") != PROJECT or release.get("SpaceId") != SPACE
            or process.get("ProjectId") != PROJECT
            or process.get("Id") != release.get("ProjectDeploymentProcessSnapshotId")):
        raise ValueError("HQ project or immutable process snapshot mismatch")
    if (deployment.get("ReleaseId") != release.get("Id")
            or deployment.get("ProjectId") != PROJECT
            or deployment.get("TaskId") != task.get("Id")
            or task.get("Arguments", {}).get("DeploymentId") != deployment.get("Id")
            or task.get("SpaceId") != SPACE):
        raise ValueError("task does not belong to the selected HQ release")
    if details.get("Task", {}).get("Id") != task.get("Id"):
        raise ValueError("activity log belongs to another task")
    outcomes = {}
    for root in details.get("ActivityLogs", []):
        for node in root.get("Children", []):
            name = node.get("Name", "")
            match = re.fullmatch(r"Step [0-9]+: (.+)", name)
            if match:
                outcomes.setdefault(match[1], []).append(node.get("Status"))
    selected = {}
    for item in release.get("SelectedGitResources", []):
        key = (item.get("ActionName"), item.get("GitResourceReferenceName", ""))
        if key in selected:
            raise ValueError("ambiguous selected Git resource")
        selected[key] = item.get("GitReferenceResource", {}).get("GitCommit")
    covered = set()
    findings = []
    for step in process.get("Steps", []):
        for action in step.get("Actions", []):
            for dependency in action.get("GitDependencies", []):
                uri = dependency.get("RepositoryUri", "")
                name = next((n for n in REPOS if uri == f"https://github.com/ayahos-hq/{n}.git"), None)
                if name is None:
                    findings.append("unexpected repository in HQ process")
                    continue
                key = (action.get("Name"), dependency.get("Name", ""))
                if selected.get(key) != expected[name]:
                    findings.append("release revision differs: " + name)
                elif (action.get("IsDisabled") or step.get("IsDisabled")
                      or step.get("Condition") != "Success"
                      or outcomes.get(step.get("Name")) != ["Success"]):
                    findings.append("source step not proven successful: " + name)
                else:
                    covered.add(name)
    findings.extend("missing source coverage: " + n for n in sorted(REPOS - covered))
    if task.get("State") != "Success":
        findings.append("release task did not succeed")
    # A green task alone is insufficient if individual actions were skipped.
    if task.get("HasWarningsOrErrors"):
        findings.append("task has warnings or errors requiring operator review")
    return {
        "schema_version": 1,
        "evidence_level": "octopus-source-coverage-only",
        "release_id": release["Id"],
        "task_id": task["Id"],
        "source_coverage_passed": not findings,
        "production_accepted": False,
        "expected_revisions": expected,
        "covered_repositories": sorted(covered),
        "findings": sorted(set(findings)),
        "remaining_acceptance": ["required integration lane outcomes", "artifact digests",
                                 "PostgreSQL and pgvector", "database restore",
                                 "authenticated live smoke", "rollback rehearsal"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).resolve().parents[1] / "release-manifest.json")
    parser.add_argument("--platform-sha", required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--task-id", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"Releases-[0-9]+", args.release_id) or not re.fullmatch(r"ServerTasks-[0-9]+", args.task_id):
        parser.error("invalid release or task ID")
    try:
        release = api(f"/api/{SPACE}/releases/{args.release_id}")
        snapshot = release.get("ProjectDeploymentProcessSnapshotId", "")
        if not re.fullmatch(r"deploymentprocess-Projects-21-s-[A-Za-z0-9-]+", snapshot):
            raise ValueError("invalid HQ process snapshot ID")
        process = api(f"/api/{SPACE}/deploymentprocesses/{snapshot}")
        task = api(f"/api/tasks/{args.task_id}")
        deployment_id = task.get("Arguments", {}).get("DeploymentId", "")
        if not re.fullmatch(r"Deployments-[0-9]+", deployment_id):
            raise ValueError("invalid deployment ID")
        deployment = api(f"/api/{SPACE}/deployments/{deployment_id}")
        details = api(f"/api/tasks/{args.task_id}/details")
        report = audit(json.loads(args.manifest.read_text(encoding="utf-8")),
                       args.platform_sha, release, process, task, deployment, details)
    except (OSError, ValueError, KeyError, TypeError):
        print("HQ AUDIT BLOCKED: invalid evidence or read-only request failed", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["source_coverage_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
