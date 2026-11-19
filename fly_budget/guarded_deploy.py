"""Single entrypoint for budget-checked Fly deploys.

Only when --execute is requested, fresh operator-attested organization
billing is supplied, and live CLI inventory proves max one small Machine.
Do not invoke Fly deployment directly from CI/Octopus; wire this preflight.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from budget_guard import (
    GateDecision,
    GateError,
    assess,
    parse_fly,
    parse_snapshot,
    verify_inventory,
)

FlyCall = Callable[[list[str]], str]


def _fly_cli(command: list[str]) -> str:
    try:
        proc = subprocess.run(command, text=True, capture_output=True, check=False, timeout=75)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GateError("Fly CLI unavailable or timed out: no release authorized") from exc
    # Never print raw provider error bodies; they can contain account data.
    if proc.returncode:
        raise GateError("Fly CLI authentication, inventory or deployment failed")
    return proc.stdout


def _read_json_response(value: str, label: str) -> object:
    try:
        return json.loads(value)
    except (TypeError, ValueError) as exc:
        raise GateError("invalid authenticated " + label + " response") from exc


def guarded_deploy(
    *, config: Path, snapshot: Path, organization: str,
    execute: bool = False,
    image_digest: str | None = None,
    now: dt.datetime | None = None,
    fly_command: FlyCall = _fly_cli,
) -> GateDecision:
    source_root = Path(__file__).resolve().parents[1]
    if snapshot.resolve().is_relative_to(source_root):
        raise GateError("private billing snapshot must be outside Git source tree")
    try:
        profile = parse_fly(config.read_text(encoding="utf-8"))
        bill = parse_snapshot(json.loads(snapshot.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise GateError("unreadable config or verified billing snapshot") from exc
    # Cost assessment comes BEFORE even a read-only call to provider APIs.
    decision = assess(profile, bill, expected_org=organization, now=now)
    apps_cmd = ["flyctl", "apps", "list", "--org", organization, "--json"]
    apps = _read_json_response(fly_command(apps_cmd), "apps list")
    if not isinstance(apps, list):
        raise GateError("unrecognized apps inventory")
    target_found = False
    machines = {}
    for app in apps:
        if not isinstance(app, dict):
            raise GateError("invalid Fly app inventory")
        name = app.get("Name", app.get("name"))
        org = app.get("Organization", app.get("organization"))
        if isinstance(org, dict):
            org = org.get("Slug", org.get("slug"))
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]{3,62}", name) or org != organization:
            raise GateError("invalid Fly app inventory")
        if name in machines:
            raise GateError("duplicate Fly app inventory")
        target_found = target_found or name == profile.app
        machines[name] = _read_json_response(
            fly_command(["flyctl", "machine", "list", "--app", name, "--json"]),
            "machine list",
        )
        volumes = _read_json_response(
            fly_command(["flyctl", "volumes", "list", "--app", name, "--json"]),
            "volume list",
        )
        if not isinstance(volumes, list) or volumes:
            raise GateError("volume inventory must be empty for every app")
    actual_apps = verify_inventory(apps, machines, organization, profile.app)
    if bill.existing_billing_apps_count != actual_apps:
        raise GateError("attested billing app count differs from authenticated inventory")
    max_mb = 256 if profile.memory == "256mb" else 512
    for machine in machines[profile.app]:
        if machine["config"]["guest"]["memory_mb"] > max_mb:
            raise GateError("live Machine exceeds proposed memory profile")
    if not execute:
        return decision
    if not target_found:
        raise GateError("no existing Fly target app; do not create a billable app implicitly")
    if (not isinstance(image_digest, str) or
            not re.fullmatch(r"registry\.fly\.io/" + re.escape(profile.app)
                             + r"@sha256:[0-9a-f]{64}", image_digest)):
        raise GateError("immutable app-specific OCI image digest required")
    # --update-only prevents implicit Machine creation; --ha=false
    # prevents spare HA capacity. Exact image avoids unpinned local builds.
    fly_command([
        "flyctl", "deploy", "--app", profile.app, "--config", str(config),
        "--ha=false", "--update-only", "--image", image_digest,
    ])
    # Post-deploy validation: duplicate Machines have occurred on Fly's API,
    # so a successful deploy exit is insufficient capacity evidence.
    latest_apps = _read_json_response(fly_command(apps_cmd), "post-deploy apps list")
    latest = {}
    for name in machines:
        latest[name] = _read_json_response(
            fly_command(["flyctl", "machine", "list", "--app", name, "--json"]),
            "post-deploy machine list",
        )
        volumes = _read_json_response(
            fly_command(["flyctl", "volumes", "list", "--app", name, "--json"]),
            "post-deploy volume list",
        )
        if not isinstance(volumes, list) or volumes:
            raise GateError("post-deploy volume inventory is not empty")
    verify_inventory(latest_apps, latest, organization, profile.app)
    return decision


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AyahOS guarded Fly deploy (never a hard cap)")
    parser.add_argument("--fly-config", type=Path, required=True)
    parser.add_argument("--billing-snapshot", type=Path, required=True)
    parser.add_argument("--organization", required=True)
    parser.add_argument("--execute", action="store_true", help="Allow an actual Fly deploy")
    parser.add_argument("--image-digest", help="Exact existing Fly registry image sha256 digest")
    args = parser.parse_args(argv)
    try:
        result = guarded_deploy(
            config=args.fly_config,
            snapshot=args.billing_snapshot,
            organization=args.organization,
            execute=args.execute,
            image_digest=args.image_digest,
        )
    except GateError as exc:
        print(json.dumps({
            "allowed": False, "reason": str(exc),
            # A provider timeout or failed post-check can occur after Fly has
            # applied the update. Never report a failed execute as no change.
            "deployment_state": "unknown_verify_fly" if args.execute else "not_attempted",
            "actual_deployment_confirmed": None if args.execute else False,
            "is_provider_hard_cap": False,
        }), file=sys.stderr)
        return 3
    from dataclasses import asdict
    data = asdict(result)
    data["fly_deploy_command_completed"] = bool(args.execute)
    data["actual_app_health_verified"] = False
    print(json.dumps(data, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
