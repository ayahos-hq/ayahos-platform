"""Fail-closed, offline Fly.io USD $5 release ADMISSION guard.

This guards AyahOS release decisions, NOT Fly's monthly invoice.
Fly.io does not offer an account-level spending cap. Input snapshots must
come from a separate authenticated, independently verified collector.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import hmac
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_UP
from pathlib import Path


class BudgetError(ValueError):
    """Evidence/configuration is untrustworthy: deny without estimating."""


@dataclass(frozen=True)
class Policy:
    organization: str
    limit_usd: Decimal
    safety_ceiling_usd: Decimal
    max_machines: int
    preset: str
    per_hour_usd: Decimal
    egress_per_gb_usd: Decimal


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    limit_usd: Decimal
    safety_ceiling_usd: Decimal
    forecast_usd: Decimal
    reasons: tuple[str, ...]
    actual_spending_hard_capped: bool = False


_POLICY_KEYS = {
    "schema_version", "organization", "monthly_budget_usd", "safety_reserve_usd",
    "max_running_machines", "allowed_machine_preset", "machine_hourly_usd",
    "egress_per_gb_usd",
}
_EVIDENCE_KEYS = {
    "schema_version", "source", "organization", "timestamp_utc",
    "billing_month_utc", "billing_to_date_usd", "billed_charges_complete",
    "all_org_apps_enumerated", "unknown_resources", "volumes_gb",
    "dedicated_ipv4", "reserved_capacity", "managed_services",
    "other_monthly_commitments_usd", "running_machines", "stopped_machines",
}
_INTENT_KEYS = {
    "schema_version", "org", "sha", "machine_preset",
    "desired_total_running_machines", "max_egress_gb_remaining_month",
    "max_certificate_usd_remaining_month",
}
_MACHINE_KEYS = {"app", "id", "preset"}


def _dict(value: object, fields: set[str], field: str) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        raise BudgetError(field + " must contain exactly the known v1 fields")
    return value


def _number(value: object, label: str, *, decimals: int = 2) -> Decimal:
    if not isinstance(value, str) or not re.fullmatch(
        r"0|[0-9]+(?:\.[0-9]{1," + str(decimals) + r"})?", value
    ):
        raise BudgetError(label + " must be a nonnegative decimal string")
    try:
        d = Decimal(value)
    except InvalidOperation as exc:
        raise BudgetError(label + " has invalid decimal") from exc
    if not d.is_finite() or d < 0 or d >= Decimal("1000000"):
        raise BudgetError(label + " outside accepted range")
    return d


def _utc_time(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise BudgetError("require exact UTC RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise BudgetError("invalid evidence timestamp") from exc
    if parsed.utcoffset() != timedelta(0):
        raise BudgetError("non-UTC timestamp")
    return parsed


def load_policy(path: Path) -> Policy:
    try:
        data = _dict(json.loads(path.read_text(encoding="utf-8")),
                     _POLICY_KEYS, "policy")
    except (OSError, ValueError, UnicodeError) as exc:
        raise BudgetError("cannot load policy") from exc
    if (type(data["schema_version"]) is not int or data["schema_version"] != 1 or
            data["organization"] != "ayahos" or
            data["allowed_machine_preset"] != "shared-cpu-1x-256mb" or
            type(data["max_running_machines"]) is not int or
            data["max_running_machines"] != 1):
        raise BudgetError("budget policy changes require explicit code review")
    limit = _number(data["monthly_budget_usd"], "monthly budget")
    reserve = _number(data["safety_reserve_usd"], "safety reserve")
    per_hour = _number(data["machine_hourly_usd"], "compute price", decimals=4)
    egress = _number(data["egress_per_gb_usd"], "network price", decimals=4)
    if (limit != Decimal("5.00") or reserve < Decimal("0.50") or
            per_hour < Decimal("0.0030") or egress < Decimal("0.02") or reserve >= limit):
        raise BudgetError("price or reserve lower than vetted safety assumptions")
    return Policy(
        organization="ayahos", limit_usd=limit,
        safety_ceiling_usd=limit - reserve,
        max_machines=1, preset="shared-cpu-1x-256mb",
        per_hour_usd=per_hour, egress_per_gb_usd=egress,
    )


def _machines(value: object, policy: Policy) -> list[dict]:
    if not isinstance(value, list) or len(value) > policy.max_machines:
        raise BudgetError("unbudgeted running Machines detected")
    ids: set[str] = set()
    for item in value:
        machine = _dict(item, _MACHINE_KEYS, "Machine")
        if (not all(isinstance(machine[x], str) and machine[x] for x in _MACHINE_KEYS)
                or machine["preset"] != policy.preset or machine["id"] in ids):
            raise BudgetError("Machine with unknown preset or identity")
        ids.add(machine["id"])
    return value


def evaluate(
    policy: Policy, evidence: dict, intent: dict, *, now: datetime,
) -> Verdict:
    if not isinstance(policy, Policy):
        raise BudgetError("missing verified policy")
    e = _dict(evidence, _EVIDENCE_KEYS, "billing evidence")
    i = _dict(intent, _INTENT_KEYS, "deployment intent")
    if e["schema_version"] != 1 or i["schema_version"] != 1:
        raise BudgetError("unknown evidence schema")
    if (e["organization"] != policy.organization or
            i["org"] != policy.organization):
        raise BudgetError("Fly billing-organization mismatch")
    if e["source"] != "verified-provider-inventory":
        raise BudgetError("provider snapshot provenance not confirmed")
    if (e["billed_charges_complete"] is not True or
            e["all_org_apps_enumerated"] is not True or
            e["unknown_resources"] is not False):
        raise BudgetError("billing or app inventory incomplete")
    if (type(e["volumes_gb"]) is not int or e["volumes_gb"] != 0 or
            type(e["dedicated_ipv4"]) is not int or e["dedicated_ipv4"] != 0 or
            e["reserved_capacity"] is not False or
            e["managed_services"] is not False or
            _number(e["other_monthly_commitments_usd"], "commitments") != 0):
        raise BudgetError("unapproved recurring-cost resource")
    if not isinstance(e["stopped_machines"], list) or e["stopped_machines"]:
        raise BudgetError("stopped Machine rootfs charges require separate accounting")
    _machines(e["running_machines"], policy)
    if (type(i["desired_total_running_machines"]) is not int or
            i["desired_total_running_machines"] != policy.max_machines or
            i["machine_preset"] != policy.preset or
            not isinstance(i["sha"], str) or not re.fullmatch(r"[0-9a-f]{40}", i["sha"])):
        raise BudgetError("deployment would exceed approved resource envelope")
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise BudgetError("caller must provide current UTC time")
    seen = _utc_time(e["timestamp_utc"])
    age = now - seen
    if not timedelta(seconds=0) <= age <= timedelta(minutes=15):
        raise BudgetError("provider snapshot stale or future-dated")
    period = f"{now.year:04d}-{now.month:02d}"
    if e["billing_month_utc"] != period:
        raise BudgetError("snapshot not for current billing period")
    billed = _number(e["billing_to_date_usd"], "billed USD")
    egress_gb = _number(i["max_egress_gb_remaining_month"], "remaining egress GB")
    certs = _number(i["max_certificate_usd_remaining_month"], "cert charges USD")
    # Fail closed if projected compute, egress, certificate or already accrued
    # charges cross the guardrail. Month boundaries are UTC calendar boundaries.
    year, month = now.year, now.month
    stop = datetime(year, month, calendar.monthrange(year, month)[1],
                    23, 59, 59, 999999, tzinfo=timezone.utc)
    hours = Decimal(str((stop - now).total_seconds())) / Decimal("3600")
    predicted = (billed + hours * policy.per_hour_usd +
                 egress_gb * policy.egress_per_gb_usd + certs)
    predicted = predicted.quantize(Decimal("0.0001"), rounding=ROUND_UP)
    reasons: tuple[str, ...] = (
        ("forecast_exceeds_safety_ceiling",)
        if predicted > policy.safety_ceiling_usd else ()
    )
    return Verdict(
        allowed=not reasons, limit_usd=policy.limit_usd,
        safety_ceiling_usd=policy.safety_ceiling_usd,
        forecast_usd=predicted, reasons=reasons,
    )


def verify_attestation(attested: object, secret: bytes) -> dict:
    """Verify HMAC of the exact provider collector output, fail closed.

    This authenticates the collector, not the accuracy of what the collector
    measured. The collector must itself authenticate Fly's inventory and bill.
    """
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise BudgetError("missing minimum-strength attestation key")
    if not isinstance(attested, dict):
        raise BudgetError("attested evidence must be an object")
    document = dict(attested)
    signature = document.pop("attestation_hmac", None)
    if not isinstance(signature, str) or not re.fullmatch(r"[a-f0-9]{64}", signature):
        raise BudgetError("provider evidence lacks valid attestation")
    canonical = json.dumps(
        document, separators=(",", ":"), sort_keys=True, ensure_ascii=False
    ).encode("utf-8")
    expected = hmac.new(secret, canonical, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise BudgetError("provider evidence attestation mismatch")
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fly $5/month admission gate, NEVER a billing hard cap")
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--intent", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        policy = load_policy(args.policy)
        envelope = json.loads(args.evidence.read_text(encoding="utf-8"))
        secret = os.environ.get("FLY_BUDGET_ATTESTATION_KEY", "").encode("utf-8")
        e = verify_attestation(envelope, secret)
        i = json.loads(args.intent.read_text(encoding="utf-8"))
        verdict = evaluate(policy, e, i, now=datetime.now(timezone.utc))
    except (BudgetError, OSError, ValueError, UnicodeError) as exc:
        print(json.dumps({"decision": "DENY", "reason": str(exc),
                          "fly_bill_hard_capped": False}))
        return 3
    print(json.dumps({
        "decision": "ALLOW" if verdict.allowed else "DENY",
        "forecast_usd": str(verdict.forecast_usd),
        "target_usd": str(verdict.limit_usd),
        "internal_safety_ceiling_usd": str(verdict.safety_ceiling_usd),
        "reasons": verdict.reasons,
        "fly_bill_hard_capped": False,
    }))
    return 0 if verdict.allowed else 3


if __name__ == "__main__":
    sys.exit(main())
