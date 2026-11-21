"""Security gate for a private, immutable-image staging observability stack."""
from __future__ import annotations

from copy import deepcopy
import unittest

from deploy.observability_staging.gate import validate_compose_model


class TestComposeGate(unittest.TestCase):
    def setUp(self) -> None:
        digest = "@sha256:" + "a" * 64
        self.model = {
            "services": {
                name: {
                    "image": f"example/{name}{digest}",
                    "ports": [{
                        "target": port,
                        "published": str(port),
                        "host_ip": "127.0.0.1",
                        "protocol": "tcp",
                    }],
                    "mem_limit": 268435456,
                    "pids_limit": 128,
                    "cap_drop": ["ALL"],
                    "security_opt": ["no-new-privileges:true"],
                } for name, port in {
                    "collector": 4318, "prometheus": 9090,
                    "loki": 3100, "grafana": 3000
                }.items()
            }
        }
        self.model["services"]["grafana"]["environment"] = {
            "GF_AUTH_ANONYMOUS_ENABLED": "false",
            "GF_SECURITY_ADMIN_PASSWORD__FILE": "/run/secrets/grafana_admin_password",
        }
        self.model["services"]["grafana"]["secrets"] = [{"source": "grafana_admin_password"}]
        self.model["secrets"] = {"grafana_admin_password": {"file": "/tmp/staging-only-admin-pass"}}

    def test_safe_locally_bound_immutable_stack_passes(self) -> None:
        validate_compose_model(self.model)

    def test_public_collector_ingress_is_rejected(self) -> None:
        self.model["services"]["collector"]["ports"][0]["host_ip"] = "0.0.0.0"
        with self.assertRaisesRegex(ValueError, "loopback"):
            validate_compose_model(self.model)

    def test_missing_host_ip_is_rejected(self) -> None:
        del self.model["services"]["collector"]["ports"][0]["host_ip"]
        with self.assertRaisesRegex(ValueError, "loopback"):
            validate_compose_model(self.model)

    def test_mutable_image_tag_is_rejected(self) -> None:
        self.model["services"]["loki"]["image"] = "grafana/loki:latest"
        with self.assertRaisesRegex(ValueError, "sha256"):
            validate_compose_model(self.model)

    def test_host_network_is_rejected(self) -> None:
        self.model["services"]["prometheus"]["network_mode"] = "host"
        with self.assertRaisesRegex(ValueError, "host network"):
            validate_compose_model(self.model)

    def test_privileged_or_docker_socket_mount_is_rejected(self) -> None:
        self.model["services"]["collector"]["privileged"] = True
        with self.assertRaisesRegex(ValueError, "privileged"):
            validate_compose_model(self.model)
        self.model["services"]["collector"].pop("privileged")
        self.model["services"]["collector"]["volumes"] = [
            {"type": "bind", "source": "/var/run/docker.sock", "target": "/var/run/docker.sock"}
        ]
        with self.assertRaisesRegex(ValueError, "Docker socket"):
            validate_compose_model(self.model)

    def test_missing_resource_caps_are_rejected(self) -> None:
        self.model["services"]["loki"].pop("mem_limit")
        with self.assertRaisesRegex(ValueError, "memory"):
            validate_compose_model(self.model)

    def test_grafana_anonymous_mode_is_rejected(self) -> None:
        self.model["services"]["grafana"]["environment"]["GF_AUTH_ANONYMOUS_ENABLED"] = "true"
        with self.assertRaisesRegex(ValueError, "anonymous"):
            validate_compose_model(self.model)

    def test_inline_admin_password_is_rejected(self) -> None:
        self.model["services"]["grafana"]["environment"]["GF_SECURITY_ADMIN_PASSWORD"] = "plaintext"
        with self.assertRaisesRegex(ValueError, "inline"):
            validate_compose_model(self.model)

    def test_extra_unknown_container_is_rejected(self) -> None:
        self.model["services"]["unreviewed"] = deepcopy(self.model["services"]["loki"])
        with self.assertRaisesRegex(ValueError, "service"):
            validate_compose_model(self.model)


if __name__ == "__main__":
    unittest.main()
