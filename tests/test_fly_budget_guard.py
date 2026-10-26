"""Fail-closed monthly Fly USD budget preflight. No live provider required."""
import copy
import json
import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from fly_budget_guard import BudgetError, evaluate, load_policy

POLICY = ROOT / "budget" / "fly-budget-policy.json"
STAMP = "2026-10-26T05:15:00Z"


def snapshot():
    return {
        "schema_version": 1, "source": "verified-provider-inventory",
        "organization": "ayahos", "timestamp_utc": STAMP,
        "billing_month_utc": "2026-10", "billing_to_date_usd": "0.00",
        "billed_charges_complete": True, "all_org_apps_enumerated": True,
        "unknown_resources": False, "volumes_gb": 0, "dedicated_ipv4": 0,
        "reserved_capacity": False, "managed_services": False,
        "other_monthly_commitments_usd": "0.00",
        "running_machines": [],
        "stopped_machines": [],
    }


def candidate():
    return {
        "schema_version": 1,
        "org": "ayahos",
        "sha": "a" * 40,
        "machine_preset": "shared-cpu-1x-256mb",
        "desired_total_running_machines": 1,
        "max_egress_gb_remaining_month": "5",
        "max_certificate_usd_remaining_month": "0.00",
    }


class BudgetGuardTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_policy(POLICY)
        self.now = datetime(2026, 10, 26, 5, 15, tzinfo=timezone.utc)

    def check(self, snap=None, intent=None):
        return evaluate(
            self.policy, snap or snapshot(), intent or candidate(), now=self.now
        )

    def test_single_micro_below_total_ceiling(self):
        verdict = self.check()
        self.assertTrue(verdict.allowed, verdict.reasons)
        self.assertEqual(verdict.limit_usd, Decimal("5.00"))
        self.assertLessEqual(verdict.forecast_usd, Decimal("4.50"))
        self.assertFalse(verdict.actual_spending_hard_capped)

    def test_unknown_or_stale_provider_evidence_denied(self):
        for change in (
            {"billed_charges_complete": False},
            {"all_org_apps_enumerated": False},
            {"unknown_resources": True},
            {"source": "unchecked-user-input"},
            {"timestamp_utc": "2026-10-26T04:30:00Z"},
            {"timestamp_utc": "2026-10-26T05:16:00Z"},
        ):
            with self.subTest(change=change):
                doc = snapshot() | change
                with self.assertRaises(BudgetError):
                    self.check(snap=doc)

    def test_expensive_machine_and_two_machines_denied(self):
        for change in (
            {"machine_preset": "shared-cpu-2x-512mb"},
            {"machine_preset": "performance-1x"},
            {"desired_total_running_machines": 2},
        ):
            with self.subTest(change=change):
                intent = candidate() | change
                with self.assertRaises(BudgetError):
                    self.check(intent=intent)

    def test_accrued_cost_near_limit_denied(self):
        doc = snapshot() | {"billing_to_date_usd": "4.40"}
        verdict = self.check(snap=doc)
        self.assertFalse(verdict.allowed)
        self.assertIn("forecast_exceeds_safety_ceiling", verdict.reasons)

    def test_forecast_includes_sustained_run_and_egress(self):
        intent = candidate() | {"max_egress_gb_remaining_month": "250"}
        verdict = self.check(intent=intent)
        self.assertFalse(verdict.allowed)

    def test_any_unapproved_cost_resource_fails_closed(self):
        for change in (
            {"volumes_gb": 1}, {"dedicated_ipv4": 1},
            {"reserved_capacity": True}, {"managed_services": True},
            {"stopped_machines": ["machine-x"]},
            {"other_monthly_commitments_usd": "1"},
        ):
            with self.subTest(change=change), self.assertRaises(BudgetError):
                self.check(snap=snapshot() | change)

    def test_manifests_cannot_override_budget(self):
        for change in (
            {"max_monthly_usd": "100"},
            {"allow_unknown_resources": True},
            {"allow_billing_overrun": True},
        ):
            with self.subTest(change=change), self.assertRaises(BudgetError):
                evaluate(self.policy, snapshot(), candidate() | change, now=self.now)

    def test_decimal_adversarial_values_rejected(self):
        for bad in ("NaN", "Infinity", "-1", "0.0000000000000000000001", 0.5, "x"):
            with self.subTest(value=bad), self.assertRaises(BudgetError):
                self.check(snap=snapshot() | {"billing_to_date_usd": bad})

    def test_cannot_accept_missing_second_org_or_mismatched_org(self):
        with self.assertRaises(BudgetError):
            self.check(snap=snapshot() | {"organization": "other-org"})
        with self.assertRaises(BudgetError):
            self.check(intent=candidate() | {"org": "other-org"})

    def test_current_inventory_requires_exact_desired_machine_count(self):
        data = snapshot() | {"running_machines": [
            {"app": "ayahos-core", "id": "x", "preset": "shared-cpu-1x-256mb"}
        ]}
        self.assertTrue(self.check(snap=data).allowed)
        with self.assertRaises(BudgetError):
            self.check(snap=data | {"running_machines": [
                {"app": "ayahos-core", "id": "x", "preset": "shared-cpu-1x-256mb"},
                {"app": "ayahos-core", "id": "y", "preset": "shared-cpu-1x-256mb"},
            ]})

    def test_calendar_month_not_30_day_average(self):
        policy = self.policy
        nov = snapshot() | {"billing_month_utc": "2026-11",
                             "timestamp_utc": "2026-11-01T00:00:00Z"}
        now = datetime(2026, 11, 1, tzinfo=timezone.utc)
        verdict = evaluate(policy, nov, candidate(), now=now)
        self.assertTrue(verdict.allowed)
        self.assertGreater(verdict.forecast_usd, Decimal("2.19"))


    def test_example_snapshot_always_denied_as_unverified(self):
        demo = ROOT / "budget" / "examples" / "sample-inventory.json"
        import subprocess
        proc = subprocess.run([
            sys.executable, str(ROOT / "scripts" / "fly_budget_guard.py"),
            "--policy", str(POLICY), "--evidence", str(demo),
            "--intent", str(ROOT / "budget" / "examples" / "sample-intent.json")
        ], capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertEqual(proc.returncode, 3)
        self.assertEqual(json.loads(proc.stdout)["decision"], "DENY")

    def test_attestation_tamper_and_missing_key_denied(self):
        from fly_budget_guard import verify_attestation
        import hashlib, hmac
        example = snapshot()
        secret = b"test-only-key-must-be-32-bytes-minimum"
        blob = json.dumps(example, separators=(",", ":"), sort_keys=True,
                          ensure_ascii=False).encode("utf-8")
        signature = hmac.new(secret, blob, hashlib.sha256).hexdigest()
        attested = example | {"attestation_hmac": signature}
        self.assertEqual(verify_attestation(attested, secret), example)
        with self.assertRaises(BudgetError):
            verify_attestation(attested | {"billing_to_date_usd": "0.01"}, secret)
        with self.assertRaises(BudgetError):
            verify_attestation(attested, b"short")
        with self.assertRaises(BudgetError):
            verify_attestation(example, secret)

    def test_cli_requires_attestation_even_if_metadata_looks_complete(self):
        import os
        import subprocess
        import tempfile
        doc = snapshot()
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "evidence.json"
            evidence.write_text(json.dumps(doc), encoding="utf-8")
            intent = ROOT / "budget" / "examples" / "sample-intent.json"
            env = dict(os.environ, FLY_BUDGET_ATTESTATION_KEY="test-long-secret-is-not-live-provider-key")
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts" / "fly_budget_guard.py"),
                "--policy", str(POLICY),
                "--evidence", str(evidence), "--intent", str(intent),
            ], capture_output=True, text=True, env=env, timeout=10)
            self.assertEqual(result.returncode, 3)
            self.assertEqual(json.loads(result.stdout)["decision"], "DENY")

if __name__ == "__main__":
    unittest.main()
