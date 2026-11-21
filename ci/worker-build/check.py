#!/usr/bin/env python3
"""Fail-closed HQ Worker Builds preview guard for a frozen platform extraction.

This *non-imported* operational overlay corrects the mutually inconsistent
production/preview KV assertions in the historical pinned guard. Never alter
SOURCE-PROVENANCE.json or copied source blobs to make builds pass.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "deploy/hq-verification-bridge/wrangler.jsonc"
EXPECTED_NAME = "ayahos-hq-verification-bridge"
EXPECTED_SOURCE = "../octopus-github-bridge/src/worker.js"
EXPECTED_REPO = "ayahos-hq/ayahos-platform"
EXPECTED_PROD_KV = "49ce086dc87f4de9a5110e5771907cb3"
EXPECTED_PREVIEW_KV = "2b5af79207114dec9989bc1d952c3c9d"
SHA = re.compile(r"^[a-f0-9]{40}$")
ID = re.compile(r"^[a-f0-9]{32}$")


def validate_build_environment(env: dict[str, str], actual_sha: str) -> None:
    if env.get("WORKERS_CI") != "1":
        raise ValueError("Not a Cloudflare Workers Builds execution")
    if env.get("AYAHOS_PREVIEW_ONLY") != "1":
        raise ValueError("Preview-only verification is mandatory")
    source_sha = env.get("WORKERS_CI_COMMIT_SHA", "")
    if not SHA.fullmatch(source_sha) or not SHA.fullmatch(actual_sha):
        raise ValueError("Workers CI SHA or checked-out git SHA is invalid")
    if source_sha != actual_sha:
        raise ValueError("Worker Builds checkout differs from triggering commit")
    branch = env.get("WORKERS_CI_BRANCH", "")
    if not branch or branch.startswith("-") or "\x00" in branch:
        raise ValueError("Missing or invalid Workers CI branch")


def _kv(kvs: object, label: str) -> str:
    if not isinstance(kvs, list) or len(kvs) != 1:
        raise ValueError(f"{label} must have exactly one TASKS KV binding")
    kv = kvs[0]
    if not isinstance(kv, dict) or kv.get("binding") != "TASKS":
        raise ValueError(f"{label} has invalid TASKS KV binding")
    value = kv.get("id")
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError(f"{label} has invalid TASKS KV id")
    return value


def validate_config(config: dict, root: Path) -> None:
    if not isinstance(config, dict):
        raise ValueError("Wrangler config must be a JSON object")
    if config.get("name") != EXPECTED_NAME or config.get("main") != EXPECTED_SOURCE:
        raise ValueError("Worker identity or reviewed source path changed")
    expected_path = root / "deploy/hq-verification-bridge" / EXPECTED_SOURCE
    if not expected_path.is_file():
        raise ValueError("Reviewed Worker implementation is missing")

    vars_ = config.get("vars")
    if not isinstance(vars_, dict):
        raise ValueError("HQ Worker authority variables missing")
    expected_vars = {
        "GITHUB_REPOSITORY": EXPECTED_REPO,
        "OCTOPUS_URL": "https://ayahos.octopus.app",
        "OCTOPUS_SPACE_ID": "Spaces-1",
        "OCTOPUS_PROJECT": "AyahOS HQ Verification",
        "OCTOPUS_ENVIRONMENT": "Development",
        "STATUS_CONTEXT": "octopus/hq-operator-verified",
    }
    if vars_ != expected_vars:
        raise ValueError("HQ Worker repository / Octopus authority or bindings changed")
    serialized = json.dumps(config).upper()
    if any(token in serialized for token in (
        "REPLACE_WITH", "GITHUB_WEBHOOK_SECRET", "GITHUB_STATUS_TOKEN",
        "OCTOPUS_API_KEY"
    )):
        raise ValueError("Secret material or placeholder is forbidden")

    production = _kv(config.get("kv_namespaces"), "production")
    preview = config.get("previews")
    if not isinstance(preview, dict):
        raise ValueError("Explicit isolated preview config is mandatory")
    isolated = _kv(preview.get("kv_namespaces"), "preview")
    if production != EXPECTED_PROD_KV:
        raise ValueError("Unexpected production TASKS KV binding")
    if isolated != EXPECTED_PREVIEW_KV or isolated == production:
        raise ValueError("preview TASKS must be separate from production KV")
    if preview.get("vars") != vars_:
        raise ValueError("Preview authority variables must match reviewed HQ settings")
    if "triggers" in preview or "triggers" in config:
        raise ValueError("Worker preview config must never carry release cron triggers")


def run() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview-only", action="store_true")
    args = parser.parse_args()
    env = dict(os.environ)
    if args.preview_only:
        env["AYAHOS_PREVIEW_ONLY"] = "1"
    sha = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    validate_build_environment(env, sha)
    validate_config(json.loads(CONFIG.read_text(encoding="utf-8")), ROOT)
    # The checked-in imported files are immutable. Their exact hashes and
    # executable modes MUST still match the frozen manifest on every build.
    subprocess.run(
        ["python3", str(ROOT / "scripts/verify-platform.py")],
        check=True, cwd=ROOT
    )
    print("HQ_WORKER_SOURCE_VERIFIED=" + sha)
    print("HQ_WORKER_DEPLOYMENT_AUTHORITY=OCTOPUS_ONLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
