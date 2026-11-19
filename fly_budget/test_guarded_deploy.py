"""No Fly deploy without price admission, authenticated inventory and pin."""
import json
import contextlib
import io
import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

from budget_guard import GateError
from guarded_deploy import guarded_deploy, main


class DeployTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.config = self.path / "fly.toml"
        self.config.write_text('''app = "ayahos-core-shadow"
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
''')
        self.ledger = self.path / "verified.json"
        self.ledger.write_text(json.dumps({
            "organization": "ayahos-test",
            "source": "authenticated_fly_billing_dashboard",
            "observed_at": "2026-10-26T04:00:00Z", "month": "2026-10",
            "spent_cents": 0, "pending_cents": 0,
            "other_resources_projected_cents": 0,
            "existing_billing_apps_count": 1,
            "attested_by_operator": True,
        }))
        self.now = __import__("datetime").datetime(2026,10,26,5,tzinfo=__import__("datetime").timezone.utc)

    def test_missing_binary_or_auth_never_deploys(self):
        seen = []
        def fake_command(cmd):
            seen.append(cmd)
            raise GateError("no authenticated Fly CLI")
        with self.assertRaises(GateError):
            guarded_deploy(config=self.config, snapshot=self.ledger,
                           organization="ayahos-test", now=self.now,
                           fly_command=fake_command, execute=True)
        self.assertFalse(any("deploy" in x for x in seen))

    def test_execute_failure_requires_live_reconciliation(self):
        output = io.StringIO()
        with patch("guarded_deploy.guarded_deploy", side_effect=GateError("post-check failed")):
            with contextlib.redirect_stderr(output):
                code = main(["--fly-config", str(self.config), "--billing-snapshot",
                             str(self.ledger), "--organization", "ayahos-test", "--execute"])
        report = json.loads(output.getvalue())
        self.assertEqual(code, 3)
        self.assertEqual(report["deployment_state"], "unknown_verify_fly")
        self.assertIsNone(report["actual_deployment_confirmed"])

    def test_stale_budget_prevents_any_fly_network_call(self):
        ledger = json.loads(self.ledger.read_text())
        ledger["spent_cents"] = 450
        self.ledger.write_text(json.dumps(ledger))
        seen = []
        with self.assertRaises(GateError):
            guarded_deploy(config=self.config, snapshot=self.ledger,
                           organization="ayahos-test", now=self.now,
                           fly_command=lambda cmd: seen.append(cmd), execute=True)
        self.assertEqual(seen, [])

    def test_staging_gate_prevents_more_than_one_machine(self):
        seen = []
        apps = [{"Name":"ayahos-core-shadow","Organization":"ayahos-test"}]
        machines = [{"id":"a","config":{"guest":{"cpu_kind":"shared","cpus":1,"memory_mb":512}}}, {"id":"b","config":{"guest":{"cpu_kind":"shared","cpus":1,"memory_mb":512}}}]
        def cmd(argv):
            seen.append(argv)
            return json.dumps(apps if "apps" in argv else [] if "volumes" in argv else machines)
        with self.assertRaises(GateError):
            guarded_deploy(config=self.config, snapshot=self.ledger,
                           organization="ayahos-test", now=self.now,
                           fly_command=cmd, execute=True)
        self.assertFalse(any("deploy" in x for x in seen))

    def test_valid_dry_run_does_not_deploy(self):
        seen = []
        apps = [{"Name":"ayahos-core-shadow","Organization":"ayahos-test"}]
        machines = [{"id":"a","config":{"guest":{"cpu_kind":"shared","cpus":1,"memory_mb":512}}}]
        def cmd(argv):
            seen.append(argv)
            return json.dumps(apps if "apps" in argv else [] if "volumes" in argv else machines)
        result = guarded_deploy(config=self.config, snapshot=self.ledger,
                                organization="ayahos-test", now=self.now,
                                fly_command=cmd, execute=False)
        self.assertTrue(result.allowed)
        self.assertFalse(any("deploy" in x for x in seen))

    def test_valid_live_deploy_only_uses_safe_args(self):
        seen = []
        apps = [{"Name":"ayahos-core-shadow","Organization":"ayahos-test"}]
        machines = [{"id":"a","config":{"guest":{"cpu_kind":"shared","cpus":1,"memory_mb":512}}}]
        def cmd(argv):
            seen.append(argv)
            if "apps" in argv:
                return json.dumps(apps)
            if "machine" in argv:
                return json.dumps(machines)
            if "volumes" in argv:
                return json.dumps([])
            return "deployment accepted"
        result = guarded_deploy(config=self.config, snapshot=self.ledger,
                                organization="ayahos-test", now=self.now,
                                fly_command=cmd, execute=True,
                                image_digest="registry.fly.io/ayahos-core-shadow@sha256:" + "a"*64)
        self.assertTrue(result.allowed)
        deploy = [x for x in seen if "deploy" in x]
        self.assertEqual(len(deploy), 1)
        self.assertIn("--ha=false", deploy[0])
        self.assertIn("--update-only", deploy[0])
        self.assertIn("--image", deploy[0])
        self.assertIn("--config", deploy[0])
        self.assertIn("ayahos-core-shadow", deploy[0])

    def test_three_apps_are_all_queried_and_extra_cost_required(self):
        snapshot = json.loads(self.ledger.read_text())
        snapshot.update(existing_billing_apps_count=3, other_resources_projected_cents=1)
        self.ledger.write_text(json.dumps(snapshot))
        names = ["ayahos-core-shadow", "ayahos-admin", "ayahos-rag"]
        apps = [{"Name": name, "Organization": {"Slug": "ayahos-test"}} for name in names]
        calls = []
        def cmd(argv):
            calls.append(argv)
            if "apps" in argv:
                return json.dumps(apps)
            if "volumes" in argv:
                return json.dumps([])
            name = argv[argv.index("--app") + 1]
            return json.dumps([{"id": name, "state": "started" if name == names[0] else "stopped",
                "config": {"guest": {"cpu_kind": "shared", "cpus": 1, "memory_mb": 512}}}])
        result = guarded_deploy(config=self.config, snapshot=self.ledger,
                                organization="ayahos-test", now=self.now, fly_command=cmd)
        self.assertTrue(result.allowed)
        self.assertEqual({c[c.index("--app") + 1] for c in calls if "machine" in c}, set(names))

        snapshot["other_resources_projected_cents"] = 0
        self.ledger.write_text(json.dumps(snapshot))
        with self.assertRaises(GateError):
            guarded_deploy(config=self.config, snapshot=self.ledger,
                           organization="ayahos-test", now=self.now, fly_command=cmd)

    def test_unattached_volume_denies_deploy(self):
        apps = [{"Name": "ayahos-core-shadow", "Organization": "ayahos-test"}]
        def cmd(argv):
            if "apps" in argv:
                return json.dumps(apps)
            if "volumes" in argv:
                return json.dumps([{"id": "unattached-volume"}])
            return json.dumps([{"id": "a", "config": {
                "guest": {"cpu_kind": "shared", "cpus": 1, "memory_mb": 512}}}])
        with self.assertRaises(GateError):
            guarded_deploy(config=self.config, snapshot=self.ledger,
                           organization="ayahos-test", now=self.now, fly_command=cmd)


    def test_execute_requires_pinned_image(self):
        apps = [{"Name":"ayahos-core-shadow","Organization":"ayahos-test"}]
        machines = [{"id":"a","config":{"guest":{"cpu_kind":"shared","cpus":1,"memory_mb":512}}}]
        calls = []
        def fly(args):
            calls.append(args)
            return json.dumps(apps if "apps" in args else [] if "volumes" in args else machines)
        with self.assertRaises(GateError):
            guarded_deploy(config=self.config,snapshot=self.ledger,
                           organization="ayahos-test",now=self.now,
                           fly_command=fly,execute=True)
        self.assertFalse(any("deploy" in a for a in calls))



if __name__ == "__main__":
    unittest.main()
