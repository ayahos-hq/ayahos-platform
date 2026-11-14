"""Render blueprint must not claim unbacked production PostgreSQL or purge history."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BLUEPRINT = ROOT / "render.yaml"


def env_default(name: str) -> str | None:
    text = BLUEPRINT.read_text(encoding="utf-8")
    match = re.search(
        rf"(?m)^\s+- key: {re.escape(name)}\s*\n\s+value:\s*[\"']?([A-Za-z0-9_-]+)",
        text,
    )
    return match.group(1) if match else None


class BlueprintDatabaseSafetyTests(unittest.TestCase):
    def test_default_runtime_storage_mode_matches_verified_live_service(self):
        # The verified live service runs on Supabase Postgres since the
        # 2026-10-23 cutover (migration 022 applied, persistence proven
        # in-database, spine_storage readback "postgres"); the blueprint
        # default must keep matching it.
        self.assertEqual("postgres", env_default("DUAL_LINEAGE_DATABASE_MODE"))

    def test_retention_must_be_explicitly_scheduled_after_restore_proof(self):
        self.assertEqual("false", env_default("DUAL_LINEAGE_SPINE_RETENTION_ON_START"))


    def test_canonical_render_services_are_release_gated(self):
        # Octopus is the authoritative release verifier, so pushes cannot
        # automatically ship an unverified SHA to production.
        text = BLUEPRINT.read_text(encoding="utf-8")
        for name in ("goblin-dual-lineage-api", "goblin-dual-lineage-web-live"):
            self.assertRegex(
                text,
                rf"(?ms)^    name: {re.escape(name)}\n"
                rf"(?:(?!^  - type:).)*?^    autoDeployTrigger: 'off'$",
                f"{name} must require an explicitly approved deployment",
            )


if __name__ == "__main__":
    unittest.main()
