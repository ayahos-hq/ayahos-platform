#!/usr/bin/env python3
"""Fail-closed exact-SHA guard for HQ Worker Builds (not Octopus release authority).

Use from the repo root with Cloudflare's WORKERS_CI_COMMIT_SHA injected by Builds.
The *separate* deploy command must be read-only on main; only previews are permitted.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "deploy" / "hq-verification-bridge" / "wrangler.jsonc"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
NAMESPACE_RE = re.compile(r"^[0-9a-f]{32}$")
EXPECTED_NAME = "ayahos-hq-verification-bridge"
EXPECTED_SOURCE = "../octopus-github-bridge/src/worker.js"
EXPECTED_REPO = "ayahos-hq/ayahos-platform"


def validate_sha(expected: str | None, actual: str) -> str:
    if not expected or not SHA_RE.fullmatch(expected):
        raise ValueError("Missing or invalid Cloudflare exact commit SHA")
    if not SHA_RE.fullmatch(actual) or expected != actual:
        raise ValueError("Worker Builds git checkout differs from triggering commit")
    return expected


def validate_build_environment(env: dict[str, str], sha: str) -> str:
    if env.get("WORKERS_CI") != "1":
        raise ValueError("Not a Workers Builds execution; deny unverified CI authority")
    if env.get("AYAHOS_PREVIEW_ONLY") != "1":
        raise ValueError("Production-deploy-capable mode is forbidden by this gate")
    branch = env.get("WORKERS_CI_BRANCH", "")
    if not branch or branch.startswith("-") or "\x00" in branch:
        raise ValueError("Invalid or missing triggering branch")
    return validate_sha(env.get("WORKERS_CI_COMMIT_SHA"), sha)


def validate_config() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if config.get("name") != EXPECTED_NAME:
        raise ValueError("Worker identity mismatches HQ verification bridge")
    if config.get("main") != EXPECTED_SOURCE:
        raise ValueError("Worker source is not pinned to the reviewed Octopus bridge")
    if config.get("vars", {}).get("GITHUB_REPOSITORY") != EXPECTED_REPO:
        raise ValueError("Webhook repository authority is not HQ platform")
    if config.get("vars", {}).get("OCTOPUS_PROJECT") != "AyahOS HQ Verification":
        raise ValueError("HQ Octopus project authority mismatch")
    if config.get("vars", {}).get("OCTOPUS_ENVIRONMENT") != "Development":
        raise ValueError("Unsupported environment for HQ preview gate")
    if config.get("vars", {}).get("STATUS_CONTEXT") != "octopus/hq-operator-verified":
        raise ValueError("HQ status context mismatch")
    if any(key in json.dumps(config).upper() for key in
           ("REPLACE_WITH", "GITHUB_WEBHOOK_SECRET", "GITHUB_STATUS_TOKEN",
            "OCTOPUS_API_KEY")):
        raise ValueError("Configuration contains placeholder or secret material")
    namespaces = config.get("kv_namespaces", [])
    if len(namespaces) != 1 or namespaces[0].get("binding") != "TASKS":
        raise ValueError("Dedicated preview tasks binding missing")
    if namespaces[0].get("id") == "49ce086dc87f4de9a5110e5771907cb3":
        raise ValueError("Production tasks KV must never be exposed to previews")
    if not NAMESPACE_RE.fullmatch(namespaces[0].get("id", "")):
        raise ValueError("Invalid preview namespace")
    previews = config.get("previews", {})
    if previews.get("vars") != config.get("vars"):
        raise ValueError("Preview variables must be declared and isolated explicitly")
    if previews.get("kv_namespaces") != namespaces:
        raise ValueError("Preview TASKS must be explicitly isolated from production")
    if "triggers" in previews:
        raise ValueError("Preview must not execute the production verification cron")
    if not (CONFIG.parent / EXPECTED_SOURCE).is_file():
        raise ValueError("Reviewed worker source is missing")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview-only", action="store_true",
                        help="Explicitly disallow any production deployment from Builds")
    parser.add_argument("--expect-sha", help="Explicit local reproduction of CI SHA")
    args = parser.parse_args()
    env = dict(os.environ)
    if args.preview_only:
        env["AYAHOS_PREVIEW_ONLY"] = "1"
    if args.expect_sha:
        env["WORKERS_CI_COMMIT_SHA"] = args.expect_sha
    result = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                            text=True, capture_output=True, check=True)
    sha = result.stdout.strip()
    validate_build_environment(env, sha)
    validate_config()
    print("HQ_WORKER_SOURCE_VERIFIED=" + sha)
    print("HQ_WORKER_DEPLOYMENT_AUTHORITY=OCTOPUS_ONLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
