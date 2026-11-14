"""Verify that the production Render blueprint keeps registry rollout disabled."""

from __future__ import annotations

from pathlib import Path

SWITCHES = (
    "DUAL_LINEAGE_REGISTRY_DISCOVERY_ENABLED",
    "DUAL_LINEAGE_REGISTRY_PUBLISHING_ENABLED",
    "DUAL_LINEAGE_REGISTRY_ROUTING_ENABLED",
    "DUAL_LINEAGE_REGISTRY_EXECUTION_ENABLED",
)


def main() -> int:
    render_path = Path(__file__).resolve().parents[1] / "render.yaml"
    lines = render_path.read_text(encoding="utf-8").splitlines()
    for switch in SWITCHES:
        try:
            key_index = next(
                index for index, line in enumerate(lines) if line.strip() == f"- key: {switch}"
            )
        except StopIteration:
            print(f"registry deployment invalid: missing {switch}")
            return 1
        following = [line.strip() for line in lines[key_index + 1 : key_index + 3]]
        if 'value: "false"' not in following:
            print(f"registry deployment invalid: {switch} must be explicitly false")
            return 1
    print("registry deployment: all rollout switches explicitly disabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
