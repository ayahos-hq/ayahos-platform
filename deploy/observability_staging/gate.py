"""Fail-closed validator for the optional OSS observability staging stack.

Designed to run against `docker compose config --format json`, before any
containers are started. No networking, credentials, or production mutation.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys

SERVICES = {
    "collector": 4318,
    "prometheus": 9090,
    "loki": 3100,
    "grafana": 3000,
}
IMMUTABLE_IMAGE = re.compile(r"^[A-Za-z0-9._/:-]+@sha256:[a-f0-9]{64}$")


def _bytes_of_memory(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        match = re.fullmatch(r"(\d+)([kKmMgG]?)", value)
        if match:
            factors = {"": 1, "k": 1024, "m": 1048576, "g": 1073741824}
            return int(match.group(1)) * factors[match.group(2).lower()]
    raise ValueError("invalid memory cap")


def validate_compose_model(model: dict[str, object]) -> None:
    """Reject public ingress, mutable images, privilege escalation and excess scope."""
    services = model.get("services")
    if not isinstance(services, dict) or set(services) != set(SERVICES):
        raise ValueError("unexpected service set")

    for name, expected_port in SERVICES.items():
        service = services[name]
        if not isinstance(service, dict):
            raise ValueError(f"{name} has invalid service configuration")
        if not IMMUTABLE_IMAGE.fullmatch(str(service.get("image", ""))):
            raise ValueError(f"{name}: image must be pinned by sha256 digest")
        if service.get("privileged"):
            raise ValueError(f"{name}: privileged containers are forbidden")
        if service.get("network_mode") == "host" or service.get("pid") == "host":
            raise ValueError(f"{name}: host network/process namespace is forbidden")
        if service.get("devices"):
            raise ValueError(f"{name}: devices are forbidden")
        if not (32 * 1048576 <= _bytes_of_memory(service.get("mem_limit")) <= 1024 * 1048576):
            raise ValueError(f"{name}: memory limit outside approved staging range")
        pids = service.get("pids_limit")
        if not isinstance(pids, int) or pids < 8 or pids > 256:
            raise ValueError(f"{name}: pids limit required and bounded")
        if "ALL" not in service.get("cap_drop", []):
            raise ValueError(f"{name}: cap_drop ALL required")
        if "no-new-privileges:true" not in service.get("security_opt", []):
            raise ValueError(f"{name}: no-new-privileges security option required")

        ports = service.get("ports")
        if not isinstance(ports, list) or len(ports) != 1:
            raise ValueError(f"{name}: exactly one loopback port is required")
        port = ports[0]
        if (
            not isinstance(port, dict)
            or port.get("host_ip") != "127.0.0.1"
            or int(port.get("target", -1)) != expected_port
            or int(port.get("published", -1)) != expected_port
            or port.get("protocol", "tcp") != "tcp"
        ):
            raise ValueError(f"{name}: only reviewed loopback TCP ingress is permitted")

        for mount in service.get("volumes", []):
            if not isinstance(mount, dict):
                raise ValueError(f"{name}: unexpected volume syntax")
            if "/var/run/docker.sock" in str(mount.get("source", "")):
                raise ValueError(f"{name}: Docker socket mounts are forbidden")

    grafana = services["grafana"]
    env = grafana.get("environment", {})
    if not isinstance(env, dict):
        raise ValueError("grafana environment must be a mapping")
    if str(env.get("GF_AUTH_ANONYMOUS_ENABLED", "")).lower() != "false":
        raise ValueError("grafana anonymous login must remain disabled")
    if "GF_SECURITY_ADMIN_PASSWORD" in env:
        raise ValueError("grafana inline admin password is forbidden")
    if env.get("GF_SECURITY_ADMIN_PASSWORD__FILE") != "/run/secrets/grafana_admin_password":
        raise ValueError("grafana admin must be configured by Docker secret file")
    secret_list = grafana.get("secrets", [])
    if not any(item.get("source") == "grafana_admin_password"
               for item in secret_list if isinstance(item, dict)):
        raise ValueError("grafana admin secret mount is required")
    secrets = model.get("secrets", {})
    if not isinstance(secrets, dict) or "grafana_admin_password" not in secrets:
        raise ValueError("grafana admin secret source is required")


def main() -> int:
    root = Path(__file__).resolve().parent
    try:
        rendered = subprocess.run(
            ["docker", "compose", "-f", str(root / "compose.yaml"), "config", "--format", "json"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        validate_compose_model(json.loads(rendered.stdout))
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired,
            ValueError, TypeError, json.JSONDecodeError) as exc:
        # Never dump the Docker Compose environment or secret paths into CI logs.
        print(f"STAGING CONFIG REJECTED: {type(exc).__name__}", file=sys.stderr)
        return 1
    print("Verified 4 immutable-image services, loopback ingress, resource caps and secret isolation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
