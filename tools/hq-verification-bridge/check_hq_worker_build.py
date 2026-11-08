#!/usr/bin/env python3
"""Validate the AyahOS HQ verification bridge build inputs.

The Cloudflare Workers Builds trigger for `ayahos-hq-verification-bridge`
runs this script first. It exists so a build fails fast and legibly when
the HQ deployment manifest drifts from the configuration that is actually
deployed in the AyahOS_HQ Cloudflare account, instead of failing later
(or worse, passing with the wrong target).

--preview-only: check the manifest and sources only. No Cloudflare or
Octopus calls, no deployment, no secrets required or read.

Expected values were read back from the deployed Worker (version 7,
account AyahOS_HQ) on 2026-11-07. Secret values are never present in the
manifest; this script fails if a secret-shaped variable appears in it.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BRIDGE_DIR = Path(__file__).resolve().parent
MANIFEST = BRIDGE_DIR / "wrangler.jsonc"

EXPECTED_NAME = "ayahos-hq-verification-bridge"
EXPECTED_VARS = {
    "GITHUB_REPOSITORY": "ayahos-hq/ayahos-platform",
    "OCTOPUS_URL": "https://ayahos.octopus.app",
    "OCTOPUS_SPACE_ID": "Spaces-1",
    "OCTOPUS_PROJECT": "AyahOS HQ Verification",
    "OCTOPUS_ENVIRONMENT": "Development",
    "STATUS_CONTEXT": "octopus/hq-operator-verified",
}
EXPECTED_KV = {"TASKS": "49ce086dc87f4de9a5110e5771907cb3"}
SECRET_SHAPED = re.compile(r"(TOKEN|SECRET|API_KEY|PASSWORD)", re.IGNORECASE)


def strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments without touching string literals."""
    out: list[str] = []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def main(argv: list[str]) -> int:
    if argv != ["--preview-only"]:
        print("usage: check_hq_worker_build.py --preview-only", file=sys.stderr)
        return 2

    failures: list[str] = []

    if not MANIFEST.is_file():
        print(f"FAIL: HQ bridge manifest missing: {MANIFEST.relative_to(REPO_ROOT)}")
        return 1
    try:
        config = json.loads(strip_jsonc(MANIFEST.read_text()))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: HQ bridge manifest is not parseable JSONC: {exc}")
        return 1

    if config.get("name") != EXPECTED_NAME:
        failures.append(
            f"worker name is {config.get('name')!r}, expected {EXPECTED_NAME!r}"
        )

    main_rel = config.get("main", "")
    if not main_rel or not (BRIDGE_DIR / main_rel).is_file():
        failures.append(
            f"main module missing: {BRIDGE_DIR.relative_to(REPO_ROOT)}/{main_rel}"
        )

    if not config.get("compatibility_date"):
        failures.append("compatibility_date missing")

    vars_ = config.get("vars", {})
    for key, expected in EXPECTED_VARS.items():
        actual = vars_.get(key)
        if actual != expected:
            failures.append(f"var {key} is {actual!r}, expected {expected!r}")
    for key in vars_:
        if SECRET_SHAPED.search(key):
            failures.append(f"secret-shaped variable {key} must not be committed in vars")

    kv = {entry.get("binding"): entry.get("id") for entry in config.get("kv_namespaces", [])}
    for binding, expected_id in EXPECTED_KV.items():
        actual_id = kv.get(binding)
        if actual_id != expected_id:
            failures.append(
                f"KV binding {binding} id is {actual_id!r}, expected the deployed namespace id"
            )

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1

    print(
        "OK: HQ verification bridge manifest matches the deployed "
        "AyahOS_HQ configuration (preview-only, no deploy performed)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
