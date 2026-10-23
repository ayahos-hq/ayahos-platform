"""Offline tests for the authenticated live-head audit."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("verify-hq-live-heads.py")
spec = importlib.util.spec_from_file_location("verify_hq_live_heads", SCRIPT)
assert spec and spec.loader
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class LiveHeadsTests(unittest.TestCase):
    def test_api_error_does_not_echo_remote_body(self) -> None:
        failed = subprocess.CompletedProcess([], 1, "", "token or private details")
        with patch.object(audit.subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(audit.AuditError, "check gh login") as raised:
                audit.gh_json("repos/ayahos-hq/ayahos-site/commits/main", "site")
        self.assertNotIn("private details", str(raised.exception))

    def test_exact_siblings_and_ancestor_platform(self) -> None:
        pinned = "a" * 40
        current = "b" * 40
        manifest = {
            "components": {
                name: {"repository": f"ayahos-hq/{name}", "git_sha": pinned}
                for name in ("ayahos-site", "ayahos-core", "ayahos-admin",
                             "ayahos-workloads", "ayahos-platform")
            }
        }

        def reply(path: str, _label: str) -> dict:
            if "/compare/" in path:
                return {"status": "ahead"}
            return {"sha": current if "ayahos-platform" in path else pinned}

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with patch.object(audit, "verify_offline"), patch.object(audit, "gh_json", side_effect=reply):
                audit.audit(path)

    def test_sibling_drift_fails_closed(self) -> None:
        pinned = "a" * 40
        manifest = {"components": {
            "ayahos-site": {"repository": "ayahos-hq/ayahos-site", "git_sha": pinned}
        }}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with patch.object(audit, "verify_offline"), patch.object(
                audit, "gh_json", return_value={"sha": "b" * 40}
            ):
                with self.assertRaisesRegex(audit.AuditError, "live head mismatch"):
                    audit.audit(path)


if __name__ == "__main__":
    unittest.main()
