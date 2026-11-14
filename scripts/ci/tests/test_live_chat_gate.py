"""Offline contract tests for the public JSON + SSE release gate."""
import importlib.util
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "live_chat_gate.py"
spec = importlib.util.spec_from_file_location("live_chat_gate", SCRIPT)
assert spec and spec.loader
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
SHA = "a" * 40

def sse(*events):
    return "".join(f"event: {name}\ndata: {json.dumps(payload)}\n\n" for name, payload in events).encode()

class FakeSite(BaseHTTPRequestHandler):
    requests = []
    broken_stream = False
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"build_sha": SHA, "source_branch": "main"}).encode())
    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeSite.requests.append((self.path, payload, self.headers.get("Authorization")))
        self.send_response(200)
        streaming = payload.get("stream", False)
        self.send_header("Content-Type", "text/event-stream" if streaming else "application/json")
        self.end_headers()
        if streaming:
            events = [("start", {}), ("delta", {"text": "STREAM_OK"})]
            if not FakeSite.broken_stream:
                events.append(("done", {"status": "completed"}))
            self.wfile.write(sse(*events))
        else:
            self.wfile.write(json.dumps({"status": "completed", "text": "OK", "provider": "node-001"}).encode())
    def log_message(self, *args):
        return

class GateTests(unittest.TestCase):
    def test_build_requires_production_branch_and_exact_sha(self):
        gate.verify_build({"build_sha": SHA, "source_branch": "main"}, SHA)
        with self.assertRaisesRegex(AssertionError, "SHA"):
            gate.verify_build({"build_sha": "b" * 40, "source_branch": "main"}, SHA)
        with self.assertRaisesRegex(AssertionError, "branch"):
            gate.verify_build({"build_sha": SHA, "source_branch": "feature"}, SHA)

    def test_json_requires_completed_nonempty_model_response(self):
        gate.verify_json({"status": "completed", "text": "OK", "provider": "node-001"})
        for bad in (
            {"status": "failed", "text": "OK", "provider": "node-001"},
            {"status": "completed", "text": "", "provider": "node-001"},
            {"status": "completed", "text": "OK"},
            {"status": "completed", "text": "OK", "provider": "public-knowledge"},
        ):
            with self.subTest(bad=bad), self.assertRaises(AssertionError):
                gate.verify_json(bad)

    def test_stream_requires_start_delta_completed_and_no_error(self):
        gate.verify_sse(sse(("start", {}), ("delta", {"text": "STREAM_OK"}), ("done", {"status": "completed"})))
        for bad in (
            sse(("start", {}), ("done", {"status": "completed"})),
            sse(("start", {}), ("delta", {"text": "hi"})),
            sse(("start", {}), ("delta", {"text": "hi"}), ("done", {"status": "failed"})),
            sse(("start", {}), ("delta", {"text": "hi"}), ("error", {"error": "down"}), ("done", {"status": "completed"})),
            b"event: delta\ndata: not-json\n\n",
        ):
            with self.subTest(bad=bad), self.assertRaises(AssertionError):
                gate.verify_sse(bad)

    def test_expected_sha_requires_full_hash(self):
        self.assertEqual(gate.validate_expected_sha(SHA), SHA)
        for bad in ("", "a" * 7, "not-a-sha", "a" * 39):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                gate.validate_expected_sha(bad)

    def test_public_origin_rejects_credentials_and_insecure_remote(self):
        self.assertEqual(gate.validate_site_url("https://ayahos.pages.dev/"), "https://ayahos.pages.dev")
        for bad in ("http://ayahos.pages.dev", "https://user:pw@ayahos.pages.dev", "https://ayahos.pages.dev/bad"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                gate.validate_site_url(bad)
        self.assertEqual(gate.validate_site_url("http://127.0.0.1:8765"), "http://127.0.0.1:8765")

    def test_octopus_production_process_has_required_post_deploy_chat_gate(self):
        root = SCRIPT.parents[2]
        process = (root / ".octopus/deployment_process.ocl").read_text()
        self.assertIn('step "public-live-chat"', process)
        gate_step = process.split('step "public-live-chat"', 1)[1]
        self.assertIn('environments = ["production"]', gate_step)
        self.assertIn('ScriptParameters = "live-chat"', gate_step)
        self.assertIn('is_required = true', gate_step)
        runner = (root / "scripts/ci/octopus_verify.sh").read_text()
        self.assertIn('live-chat)', runner)
        self.assertIn('scripts/ci/live_chat_gate.py', runner)
    def test_main_passes_only_both_real_http_paths_with_no_credentials(self):
        with ThreadingHTTPServer(("127.0.0.1", 0), FakeSite) as server, tempfile.TemporaryDirectory() as temp:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            FakeSite.requests.clear()
            FakeSite.broken_stream = False
            output = str(Path(temp) / "evidence.json")
            env = {"EXPECTED_SHA": SHA, "LIVE_PUBLIC_SITE_URL": f"http://127.0.0.1:{server.server_port}", "LIVE_CHAT_GATE_OUTPUT": output}
            try:
                with patch.dict(os.environ, env):
                    self.assertEqual(gate.main(), 0)
                report = json.loads(Path(output).read_text())
                self.assertEqual(report["decision"], "PASS")
                self.assertEqual([c["check"] for c in report["checks"]], ["public_build_sha", "public_chat_json", "public_chat_sse"])
                self.assertEqual([r[1].get("stream") for r in FakeSite.requests], [None, True])
                self.assertTrue(all(auth is None for _, _, auth in FakeSite.requests))
                FakeSite.broken_stream = True
                with patch.dict(os.environ, env):
                    self.assertEqual(gate.main(), 1)
                self.assertEqual(json.loads(Path(output).read_text())["decision"], "HOLD")
            finally:
                FakeSite.broken_stream = False
                server.shutdown()

if __name__ == "__main__":
    unittest.main()
