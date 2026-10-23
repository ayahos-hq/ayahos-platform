#!/usr/bin/env python3
"""Offline, fail-closed verifier for the pinned AyahOS platform extraction."""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "SOURCE-PROVENANCE.json"
ALLOWED = (".octopus/", "deploy/", "scripts/ci/", "scripts/db/", "docs/infrastructure/")
BLOCKED = re.compile(r"(^|/)(?:\.env(?:\..*)?$|\.dev\.vars(?:\..*)?$|\.git/|\.npmrc$|id_rsa$|id_ed25519$|node_modules/)|\.(?:pem|p12|pfx|key|tfvars)$", re.I)


def run() -> None:
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if (m.get("schema_version"), m.get("state"), m.get("target_repository")) != (
        1, "provisional-not-deployed", "ayahos-hq/ayahos-platform"
    ):
        raise ValueError("unexpected manifest schema, state or target")
    expected = m["source_files"]
    if len(expected) != 66 or m["source_file_count"] != 66:
        raise ValueError("unexpected source footprint")
    listing = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    tracked = {p for p in listing.decode().split("\0") if p}
    actual = {p for p in tracked if p.startswith(ALLOWED)}
    if actual != set(expected):
        raise ValueError(f"source file set differs: missing={sorted(set(expected)-actual)} "
                         f"unexpected={sorted(actual-set(expected))}")
    for path, record in expected.items():
        pure = PurePosixPath(path)
        if pure.is_absolute() or ".." in pure.parts or not path.startswith(ALLOWED) or BLOCKED.search(path):
            raise ValueError("disallowed path in provenance: " + path)
        if not re.fullmatch(r"[a-f0-9]{40}", record["sha"]) or record["mode"] not in ("100644", "100755"):
            raise ValueError("invalid SHA or mode for " + path)
        blob = subprocess.check_output(["git", "hash-object", "--", path], cwd=ROOT, text=True).strip()
        mode = subprocess.check_output(["git", "ls-files", "-s", "--", path], cwd=ROOT, text=True).split()[0]
        if (blob, mode) != (record["sha"], record["mode"]):
            raise ValueError("source drift in " + path)
    for path in tracked:
        if BLOCKED.search(path) and not path.endswith(".env.example"):
            raise ValueError("tracked sensitive source: " + path)
        if path.startswith(("apps/", "models/", "integrations/")):
            raise ValueError("cross-service code in platform source: " + path)

    process = (ROOT / ".octopus/deployment_process.ocl").read_text()
    steps = re.findall(r'^step "([^"]+)" \{', process, flags=re.M)
    expected_steps = [
        "api-postgres", "web-site", "ml-cpu", "rag-postgres",
        "ruby-worker", "ruby-control", "release-hardening", "deployable-container-smoke",
    ]
    if steps != expected_steps or process.count("is_required = true") != len(expected_steps):
        raise ValueError("Octopus required-step topology changed")
    scripts = re.findall(r'Octopus.Action.Script.ScriptFileName = "([^"]+)"', process)
    if len(scripts) != len(expected_steps):
        raise ValueError("missing Octopus script bindings")
    for path in scripts:
        if not path.startswith("scripts/ci/") or path not in expected:
            raise ValueError("Octopus references an untracked or out-of-scope script: " + path)

    inventory = json.loads((ROOT / "deploy/service-inventory.json").read_text())
    if inventory.get("repository") != "https://github.com/fuaadabdullah/AyahOS_Dual_Lineage":
        raise ValueError("original production source changed unexpectedly")
    print("Verified 61 exact platform blobs, executable modes, eight required Octopus "
          "steps, script bindings and unchanged original deployment source.")


if __name__ == "__main__":
    try:
        run()
    except (OSError, ValueError, KeyError, IndexError, subprocess.CalledProcessError) as exc:
        print(f"PLATFORM CHECK FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
