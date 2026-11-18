"""Fail-closed AyahOS Fly.io budget advisory and deploy preflight.

This is NOT a provider-enforced spending cap. It can block the guarded
release path but cannot stop off-path deployments, delayed fees or traffic.
Never obtain Fly credentials here; only accept operator-verified snapshots.
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib

CAP_CENTS = 500
NON_COMPUTE_RESERVE_CENTS = 75
MAX_SNAPSHOT_AGE = dt.timedelta(hours=6)
PER_30_DAY_CENTS = {"256mb": 219, "512mb": 369}
_ALLOWED_REGIONS = frozenset(("iad", "ewr"))
_ALLOWED_TOP = frozenset(("app", "primary_region", "env", "http_service", "vm", "build", "deploy"))
_APP_PATTERN = re.compile(r"^[a-z][a-z0-9-]{3,62}$")
_ORG_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,62}$")


class GateError(ValueError):
    """The user budget or mandatory evidence forbids release admission."""


@dataclass(frozen=True)
class FlyProfile:
    app: str
    region: str
    memory: str
    cpu_kind: str = "shared"
    cpus: int = 1
    min_machines_running: int = 0
    auto_stop: str = "stop"


@dataclass(frozen=True)
class BillingSnapshot:
    organization: str
    observed_at: dt.datetime
    month: str
    spent_cents: int
    pending_cents: int
    other_resources_projected_cents: int
    existing_billing_apps_count: int


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    app: str
    monthly_cap_cents: int
    projected_monthly_cents: int
    remaining_headroom_cents: int
    reserve_cents: int
    is_provider_hard_cap: bool
    warning: str


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GateError(message)


def parse_fly(config_text: str) -> FlyProfile:
    try:
        content = tomllib.loads(config_text)
    except (ValueError, TypeError) as exc:
        raise GateError("unreadable fly.toml") from exc
    _require(isinstance(content, dict) and set(content) <= _ALLOWED_TOP,
             "unrecognized or billable Fly resource configuration")
    app = content.get("app")
    region = content.get("primary_region")
    _require(isinstance(app, str) and _APP_PATTERN.fullmatch(app) is not None,
             "unsafe app name")
    _require(isinstance(region, str) and region in _ALLOWED_REGIONS,
             "Fly pricing is only attested for iad/ewr")
    _require(content.get("env") == {"DUAL_LINEAGE_COMPACT_COGNITION_MODE": "shadow"},
             "only isolated shadow deployment is authorized")
    web = content.get("http_service")
    _require(isinstance(web, dict), "one HTTP service required")
    required_web = {"internal_port", "force_https", "auto_stop_machines",
                    "auto_start_machines", "min_machines_running"}
    _require(required_web <= set(web) <= required_web | {"checks"},
             "HTTP config includes unsafe or unmeasured resources")
    if "checks" in web:
        _require(web["checks"] == [{
            "interval": "30s", "timeout": "5s", "grace_period": "30s",
            "method": "GET", "path": "/health",
        }], "unsupported health check configuration")
    if "deploy" in content:
        _require(content["deploy"] == {"strategy": "immediate"},
                 "unsupported deployment strategy")
    _require(type(web["internal_port"]) is int and 1024 <= web["internal_port"] <= 65535,
             "invalid internal port")
    _require(web["force_https"] is True and
             (web["auto_stop_machines"] == "stop" or web["auto_stop_machines"] is True)
             and web["auto_start_machines"] is True
             and type(web["min_machines_running"]) is int
             and web["min_machines_running"] in (0, 1),
             "auto-stop and at most one minimum Machine required")
    vms = content.get("vm")
    _require(isinstance(vms, list) and len(vms) == 1 and isinstance(vms[0], dict),
             "exactly one VM profile required")
    vm = vms[0]
    _require(set(vm) == {"cpu_kind", "cpus", "memory"}, "unpriced VM features")
    _require(vm["cpu_kind"] == "shared" and type(vm["cpus"]) is int and vm["cpus"] == 1,
             "only shared-cpu-1x allowed")
    _require(isinstance(vm["memory"], str) and vm["memory"] in PER_30_DAY_CENTS,
             "only 256 MB / 512 MB memory supported")
    build = content.get("build", {})
    _require(isinstance(build, dict) and set(build) <= {"dockerfile"},
             "only pre-reviewed Dockerfile build permitted")
    if "dockerfile" in build:
        _require(build["dockerfile"] in ("Dockerfile", "Dockerfile.fly"),
                 "custom Dockerfile path disallowed")
    return FlyProfile(app=app, region=region, memory=vm["memory"],
                      min_machines_running=web["min_machines_running"])


def _int_field(data: dict, name: str, max_value: int = 100_000) -> int:
    v = data.get(name)
    _require(type(v) is int and 0 <= v <= max_value, "invalid billing integer: " + name)
    return v


def parse_snapshot(data: dict[str, Any]) -> BillingSnapshot:
    _require(isinstance(data, dict), "billing snapshot must be an object")
    expected = {"organization", "source", "observed_at", "month",
                "spent_cents", "pending_cents", "other_resources_projected_cents",
                "existing_billing_apps_count", "attested_by_operator"}
    _require(set(data) == expected, "missing or unknown billing snapshot fields")
    org = data["organization"]
    _require(isinstance(org, str) and _ORG_PATTERN.fullmatch(org) is not None,
             "invalid organization slug")
    _require(data["source"] == "authenticated_fly_billing_dashboard"
             and data["attested_by_operator"] is True,
             "operator-attested authenticated source required")
    stamp = data["observed_at"]
    _require(isinstance(stamp, str), "timestamp missing")
    try:
        observed = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GateError("invalid timestamp") from exc
    _require(observed.tzinfo is not None and observed.utcoffset() is not None,
             "timestamp timezone required")
    month = data["month"]
    _require(isinstance(month, str) and re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", month),
             "invalid invoice month")
    return BillingSnapshot(
        organization=org, observed_at=observed, month=month,
        spent_cents=_int_field(data, "spent_cents"),
        pending_cents=_int_field(data, "pending_cents"),
        other_resources_projected_cents=_int_field(data, "other_resources_projected_cents"),
        existing_billing_apps_count=_int_field(data, "existing_billing_apps_count", 100),
    )


def assess(
    profile: FlyProfile, snapshot: BillingSnapshot | None,
    *, expected_org: str, now: dt.datetime | None = None,
) -> GateDecision:
    _require(isinstance(profile, FlyProfile), "unverified app profile")
    _require(isinstance(snapshot, BillingSnapshot), "authenticated billing snapshot required")
    _require(isinstance(expected_org, str) and snapshot.organization == expected_org,
             "organization mismatch")
    now = now or dt.datetime.now(dt.timezone.utc)
    _require(now.tzinfo is not None and now.utcoffset() is not None,
             "timezone required")
    observed = snapshot.observed_at.astimezone(dt.timezone.utc)
    utc_now = now.astimezone(dt.timezone.utc)
    _require(dt.timedelta(minutes=-5) <= utc_now - observed <= MAX_SNAPSHOT_AGE,
             "billing snapshot is stale or in the future")
    _require(snapshot.month == utc_now.strftime("%Y-%m"), "billing month mismatch")
    _require(snapshot.existing_billing_apps_count <= 3,
             "more than three Fly apps requires independent reconciliation")
    _require(snapshot.existing_billing_apps_count <= 1
             or snapshot.other_resources_projected_cents > 0,
             "additional apps require a nonzero projected-cost allowance")
    # Accrued usage is already in the snapshot. Forecast the target from the
    # earlier of observation and now, rounding up to whole remaining days.
    start = min(observed, utc_now)
    days_in_month = calendar.monthrange(start.year, start.month)[1]
    remaining_days = days_in_month - start.day + 1
    worst_machine = (PER_30_DAY_CENTS[profile.memory] * remaining_days + 29) // 30
    projected = (snapshot.spent_cents + snapshot.pending_cents
                 + snapshot.other_resources_projected_cents + worst_machine
                 + NON_COMPUTE_RESERVE_CENTS)
    _require(projected <= CAP_CENTS,
             "DENY: projected organization spend plus safety reserve exceeds $5")
    return GateDecision(
        allowed=True, app=profile.app, monthly_cap_cents=CAP_CENTS,
        projected_monthly_cents=projected,
        remaining_headroom_cents=CAP_CENTS - projected,
        reserve_cents=NON_COMPUTE_RESERVE_CENTS,
        is_provider_hard_cap=False,
        warning=("This is not a Fly.io account-level hard cap. Unobserved usage, "
                 "delayed billing and out-of-band deploys can exceed $5."),
    )


def verify_inventory(
    apps: object, machines: object, expected_org: str, expected_app: str,
) -> int:
    """Validate complete authenticated Fly organization inventory.

    This function cannot authenticate by itself. The caller must obtain both
    lists through the active authenticated flyctl session at deploy time.
    """
    _require(isinstance(apps, list) and isinstance(machines, dict),
             "live Fly org and Machine lists are both required")
    _require(_ORG_PATTERN.fullmatch(expected_org) is not None
             and _APP_PATTERN.fullmatch(expected_app) is not None,
             "invalid expected deployment scope")
    names = set()
    for row in apps:
        _require(isinstance(row, dict), "bad Fly app inventory")
        name = row.get("Name", row.get("name"))
        org = row.get("Organization", row.get("organization"))
        if isinstance(org, dict):
            org = org.get("Slug", org.get("slug"))
        _require(isinstance(name, str) and _APP_PATTERN.fullmatch(name) is not None
                 and org == expected_org, "unexpected Fly billing organization")
        _require(name not in names, "duplicate Fly app inventory")
        names.add(name)
    _require(expected_app in names and len(names) <= 3,
             "target app missing or more than three apps")
    _require(set(machines) == names and all(isinstance(v, list) for v in machines.values()),
             "complete per-app Machine inventory required")
    _require(len(machines[expected_app]) == 1,
             "exactly one target Machine required")
    for name, records in machines.items():
        for machine in records:
            _require(isinstance(machine, dict)
                     and isinstance(machine.get("id", machine.get("ID")), str)
                     and len(machine.get("id", machine.get("ID"))) > 0,
                     "unverifiable Fly Machine identity")
            # Verify actual runtime size, not merely the desired fly.toml.
            config = machine.get("config")
            guest = config.get("guest") if isinstance(config, dict) else None
            _require(isinstance(guest, dict)
                     and guest.get("cpu_kind") == "shared"
                     and type(guest.get("cpus")) is int and guest["cpus"] == 1
                     and type(guest.get("memory_mb")) is int
                     and 0 < guest["memory_mb"] <= (512 if name == expected_app else 1024),
                     "live Machine shape cannot be proven within budget")
            _require(not config.get("mounts"), "paid volumes are not admitted")
            if name != expected_app:
                _require(machine.get("state") == "stopped",
                         "additional app Machines must be stopped")
    return len(names)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fly.io source-only $5 release admission gate")
    parser.add_argument("--fly-config", type=Path, required=True)
    parser.add_argument("--billing-snapshot", type=Path, required=True)
    parser.add_argument("--organization", required=True)
    args = parser.parse_args(argv)
    try:
        profile = parse_fly(args.fly_config.read_text(encoding="utf-8"))
        bill = parse_snapshot(json.loads(args.billing_snapshot.read_text(encoding="utf-8")))
        decision = assess(profile, bill, expected_org=args.organization)
    except (GateError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"allowed": False, "reason": str(exc),
                          "is_provider_hard_cap": False}), file=sys.stderr)
        return 3
    from dataclasses import asdict
    print(json.dumps(asdict(decision), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
