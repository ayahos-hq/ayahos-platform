"""Regression tests from authenticated Fly API/CLI inventory and Core release config."""
import unittest

from budget_guard import GateError, parse_fly, verify_inventory


class FlyLiveSchemaTests(unittest.TestCase):
    def test_real_cli_nested_organization_is_supported_for_target_app(self):
        apps = [{
            "Name": "ayahos-control-api",
            "Status": "pending",
            "Organization": {"Slug": "ayahos", "Name": "AyahOS"},
        }]
        self.assertEqual(verify_inventory(apps, [], "ayahos", "ayahos-control-api"), 1)

    def test_real_cli_nested_organization_mismatch_denied(self):
        apps = [{"Name": "ayahos-control-api", "Organization": {"Slug": "wrong-org"}}]
        with self.assertRaises(GateError):
            verify_inventory(apps, [], "ayahos", "ayahos-control-api")

    def test_reviewed_core_fly_dockerfile_with_health_probe_allowed(self):
        template = '''
app = "ayahos-control-api"
primary_region = "iad"
[build]
dockerfile = "Dockerfile.fly"
[env]
DUAL_LINEAGE_COMPACT_COGNITION_MODE = "shadow"
[http_service]
internal_port = 8000
force_https = true
auto_stop_machines = "stop"
auto_start_machines = true
min_machines_running = 0
[[http_service.checks]]
method = "GET"
path = "/health"
interval = "30s"
timeout = "5s"
grace_period = "30s"
[[vm]]
cpu_kind = "shared"
cpus = 1
memory = "512mb"
'''
        profile = parse_fly(template)
        self.assertEqual(profile.app, "ayahos-control-api")
        for altered in (
            template.replace("Dockerfile.fly", "../Dockerfile.fly"),
            template.replace('path = "/health"', 'path = "/admin"'),
            template.replace('method = "GET"', 'method = "POST"'),
        ):
            with self.subTest(altered=altered[-150:]), self.assertRaises(GateError):
                parse_fly(altered)


if __name__ == "__main__":
    unittest.main()
