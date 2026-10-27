"""Fly $5/month pre-deployment guard; default-deny for unknown spending."""
import datetime as dt
import unittest

from budget_guard import GateError, assess, parse_fly, parse_snapshot

GOOD_TOML = """
app = "ayahos-core-shadow"
primary_region = "iad"

[env]
DUAL_LINEAGE_COMPACT_COGNITION_MODE = "shadow"

[http_service]
internal_port = 8080
force_https = true
auto_stop_machines = "stop"
auto_start_machines = true
min_machines_running = 0

[[vm]]
cpu_kind = "shared"
cpus = 1
memory = "512mb"
"""
NOW = dt.datetime(2026, 10, 26, 5, tzinfo=dt.timezone.utc)
SNAP = {
    "organization": "ayahos-test",
    "source": "authenticated_fly_billing_dashboard",
    "observed_at": "2026-10-26T04:00:00Z",
    "month": "2026-10",
    "spent_cents": 0,
    "pending_cents": 0,
    "other_resources_projected_cents": 0,
    "existing_billing_apps_count": 0,
    "attested_by_operator": True,
}


def read(doc: str = GOOD_TOML):
    return parse_fly(doc)


class BudgetTests(unittest.TestCase):
    def test_one_512mb_machine_passes_only_with_fresh_evidence(self):
        gate = assess(read(), parse_snapshot(SNAP), expected_org="ayahos-test", now=NOW)
        self.assertTrue(gate.allowed)
        self.assertLessEqual(gate.projected_monthly_cents, 500)
        self.assertEqual(gate.monthly_cap_cents, 500)
        self.assertFalse(gate.is_provider_hard_cap)

    def test_off_by_default_for_missing_ledger_and_wrong_org(self):
        with self.assertRaises(GateError):
            assess(read(), None, expected_org="ayahos-test", now=NOW)
        with self.assertRaises(GateError):
            assess(read(), parse_snapshot(SNAP), expected_org="wrong-org", now=NOW)

    def test_past_month_and_stale_snapshot_fail(self):
        for delta in ("2026-09", "2026-11"):
            bad = SNAP | {"month": delta}
            with self.subTest(delta=delta), self.assertRaises(GateError):
                assess(read(), parse_snapshot(bad), expected_org="ayahos-test", now=NOW)
        old = SNAP | {"observed_at": "2026-10-25T18:00:00Z"}
        with self.assertRaises(GateError):
            assess(read(), parse_snapshot(old), expected_org="ayahos-test", now=NOW)

    def test_pending_usage_and_headroom_reserve(self):
        case = SNAP | {"spent_cents": 115, "pending_cents": 20}
        with self.assertRaises(GateError):
            assess(read(), parse_snapshot(case), expected_org="ayahos-test", now=NOW)

    def test_256mb_lower_estimate(self):
        config = GOOD_TOML.replace('memory = "512mb"', 'memory = "256mb"')
        result = assess(read(config), parse_snapshot(SNAP), expected_org="ayahos-test", now=NOW)
        self.assertTrue(result.allowed)
        self.assertLess(result.projected_monthly_cents, 400)

    def test_second_app_is_denied_until_finops_reconciles(self):
        with self.assertRaises(GateError):
            assess(read(), parse_snapshot(SNAP | {"existing_billing_apps_count": 2}),
                   expected_org="ayahos-test", now=NOW)

    def test_unknown_or_paid_machine_features_refused(self):
        wrong = [
            GOOD_TOML.replace('auto_stop_machines = "stop"', 'auto_stop_machines = "off"'),
            GOOD_TOML.replace('min_machines_running = 0', 'min_machines_running = 1'),
            GOOD_TOML.replace('auto_start_machines = true', 'auto_start_machines = false'),
            GOOD_TOML.replace('force_https = true', 'force_https = false'),
            GOOD_TOML.replace('cpu_kind = "shared"', 'cpu_kind = "performance"'),
            GOOD_TOML.replace('cpus = 1', 'cpus = 2'),
            GOOD_TOML.replace('memory = "512mb"', 'memory = "1gb"'),
            GOOD_TOML.replace('primary_region = "iad"', 'primary_region = "sin"'),
            GOOD_TOML + '\n[[mounts]]\nsource = "data"\ndestination = "/data"\n',
            GOOD_TOML + '\n[[vm]]\ncpu_kind = "shared"\ncpus = 1\nmemory = "512mb"\n',
            GOOD_TOML.replace('app = "ayahos-core-shadow"', 'app = "different-org/app"'),
        ]
        for text in wrong:
            with self.subTest(text=text[-75:]), self.assertRaises(GateError):
                parse_fly(text)

    def test_production_unsupported_until_real_runbook(self):
        with self.assertRaises(GateError):
            parse_fly(GOOD_TOML.replace('"shadow"', '"enforce"'))

    def test_user_supplied_numbers_must_not_be_boolean_or_negative(self):
        for value in (True, -1, 1.5, "0"):
            with self.subTest(value=value), self.assertRaises(GateError):
                parse_snapshot(SNAP | {"spent_cents": value})

    def test_no_false_claim_of_billing_hard_cap(self):
        report = assess(read(), parse_snapshot(SNAP), expected_org="ayahos-test", now=NOW)
        self.assertIn("not", report.warning.lower())


    def test_existing_target_app_is_permitted_if_only_one_machine(self):
        from budget_guard import verify_inventory

        apps = [{"Name": "ayahos-core-shadow", "Organization": "ayahos-test"}]
        machines = [{"id": "abcd", "state": "started", "config": {"guest": {"cpu_kind": "shared", "cpus": 1, "memory_mb": 512}, "mounts": []}}]
        self.assertEqual(verify_inventory(apps, machines, "ayahos-test",
                                          "ayahos-core-shadow"), 1)
        bad = SNAP | {"existing_billing_apps_count": 1}
        self.assertTrue(assess(read(), parse_snapshot(bad),
                               expected_org="ayahos-test", now=NOW).allowed)

    def test_multiple_machine_or_other_apps_fails_closed(self):
        from budget_guard import verify_inventory

        app = [{"Name": "ayahos-core-shadow", "Organization": "ayahos-test"}]
        for apps, machines in (
            (app, [{"id": "a"}, {"id": "b"}]),
            (app + [{"Name": "other", "Organization": "ayahos-test"}], []),
            ([{"Name": "other", "Organization": "ayahos-test"}], []),
            ([{"Name": "ayahos-core-shadow", "Organization": "other-org"}], []),
        ):
            with self.subTest(apps=apps), self.assertRaises(GateError):
                verify_inventory(apps, machines, "ayahos-test", "ayahos-core-shadow")

    def test_truncated_or_unexpected_inventory_denied(self):
        from budget_guard import verify_inventory

        for apps, machines in ((None, []), ([], None), ({}, []),
                               ([{"Name": "ayahos-core-shadow"}], [])):
            with self.assertRaises(GateError):
                verify_inventory(apps, machines, "ayahos-test", "ayahos-core-shadow")

    def test_cost_snapshot_one_existing_target_not_two(self):
        permitted = SNAP | {"existing_billing_apps_count": 1}
        self.assertTrue(assess(read(), parse_snapshot(permitted),
                               expected_org="ayahos-test", now=NOW).allowed)
        with self.assertRaises(GateError):
            assess(read(), parse_snapshot(permitted |
                   {"existing_billing_apps_count": 2}),
                   expected_org="ayahos-test", now=NOW)


if __name__ == "__main__":
    unittest.main()
