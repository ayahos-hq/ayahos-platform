"""Offline checks for the private staging smoke's authorization boundary."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import importlib.util
from pathlib import Path
from threading import Thread
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fly_otel_smoke", ROOT / "smoke.py")
assert spec and spec.loader
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class FlySmokeTests(unittest.TestCase):
    def test_authenticated_request_does_not_follow_redirect(self) -> None:
        followed: list[str] = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args) -> None:
                pass

            def do_POST(self) -> None:
                self.send_response(302)
                self.send_header("Location", "/unexpected")
                self.end_headers()

            def do_GET(self) -> None:
                followed.append(self.path)
                self.send_response(200)
                self.end_headers()

        with HTTPServer(("127.0.0.1", 0), Handler) as server:
            thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}/v1/metrics"
                self.assertEqual(smoke._request(url, {}, "x" * 32), 302)
            finally:
                server.shutdown()
                thread.join()
        self.assertEqual(followed, [])

    def test_missing_token_prevents_any_network_call(self) -> None:
        with patch.dict(smoke.os.environ, {}, clear=True), patch.object(smoke, "_request") as request:
            with self.assertRaisesRegex(ValueError, "protected collector token"):
                smoke.main()
            request.assert_not_called()

    def test_anonymous_acceptance_stops_before_authenticated_writes(self) -> None:
        with patch.object(smoke, "_token", return_value="x" * 32), patch.object(
            smoke, "_request", return_value=200
        ) as request:
            with self.assertRaisesRegex(RuntimeError, "unauthenticated"):
                smoke.main()
            self.assertEqual(request.call_count, 1)
            self.assertIsNone(request.call_args.args[2])

    def test_synthetic_payload_contains_only_expected_metadata(self) -> None:
        name = "ayahos-fly-smoke-test"
        metric = smoke._metric(name, 10_000_000)
        logs = smoke._logs(name, 10_000_000)
        self.assertEqual(len(logs["resourceLogs"][0]["scopeLogs"][0]["logRecords"]), 200)
        self.assertIn(name, str(metric))
        self.assertIn(name, str(logs))
        self.assertNotIn("prompt", str(metric).lower() + str(logs).lower())

    def test_success_requires_both_anonymous_rejections_and_exact_backend_counts(self) -> None:
        calls: list[tuple[str, str | None]] = []

        def request(url: str, _payload: dict, token: str | None) -> int:
            calls.append((url, token))
            return 401 if token is None else 200

        with patch.object(smoke, "_token", return_value="x" * 32), patch.object(
            smoke, "_request", side_effect=request
        ), patch.object(smoke, "_query", return_value=200.0):
            self.assertEqual(smoke.main(), 0)
        self.assertEqual(len(calls), 203)
        self.assertTrue(all(token is None for _, token in calls[:2]))
        self.assertTrue(all(token == "x" * 32 for _, token in calls[2:]))


if __name__ == "__main__":
    unittest.main()
