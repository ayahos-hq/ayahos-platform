"""Verify the Agent Registry configuration contract without contacting providers."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api" / "src"))

from dual_lineage.integrations.agent_registry.rollout import RegistryRolloutConfig


def main() -> int:
    config = RegistryRolloutConfig.from_env()
    base_url = os.getenv("DUAL_LINEAGE_REGISTRY_BASE_URL", "").strip()
    token = os.getenv("DUAL_LINEAGE_REGISTRY_TOKEN", "").strip()
    project_id = os.getenv("DUAL_LINEAGE_REGISTRY_PROJECT_ID", "").strip()
    snapshot_path = os.getenv("DUAL_LINEAGE_REGISTRY_SNAPSHOT_PATH", "").strip()
    snapshot_key = os.getenv("DUAL_LINEAGE_REGISTRY_SNAPSHOT_KEY", "")
    if config.can_discover() and not base_url:
        print("registry config invalid: discovery requires DUAL_LINEAGE_REGISTRY_BASE_URL")
        return 1
    if config.can_discover() and not token:
        print("registry config invalid: discovery requires a protected registry token")
        return 1
    if config.can_discover() and not project_id:
        print("registry config invalid: discovery requires DUAL_LINEAGE_REGISTRY_PROJECT_ID")
        return 1
    if base_url and not base_url.startswith("https://"):
        print("registry config invalid: DUAL_LINEAGE_REGISTRY_BASE_URL must use HTTPS")
        return 1
    if bool(snapshot_path) != bool(snapshot_key):
        print("registry config invalid: signed snapshot path and key must be configured together")
        return 1
    print(f"registry config: evidence_level={config.evidence_level.value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
