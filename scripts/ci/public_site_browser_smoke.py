#!/usr/bin/env python3
"""Browser-level smoke for an already deployed public AyahOS main-branch site.

No live cognition request is sent: Playwright intercepts /api/chat and returns a
deterministic fixture. This proves browser rendering, the composer, and client
response handling, not the production compute provider or end-to-end inference.
Use scripts/public_chat_smoke.rb separately for a real backend probe.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright


def main() -> int:
    url = os.environ.get("LIVE_PUBLIC_SITE_URL", "https://ayahos.pages.dev").rstrip("/")
    expected_sha = os.environ.get("EXPECTED_SHA", "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise ValueError("EXPECTED_SHA must be the full 40-character release commit SHA")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("LIVE_PUBLIC_SITE_URL must be an HTTPS URL with no embedded credentials")

    # Fail closed rather than testing an unrelated/stale production deployment.
    # Cloudflare bot rules can reject Python's default urllib user-agent.
    # Use the same identifiable, secret-free header as live_release_smoke.rb.
    build_request = urllib.request.Request(
        f"{url}/api/build",
        headers={"Accept": "application/json", "User-Agent": "AyahOS-live-smoke/1"},
    )
    with urllib.request.urlopen(build_request, timeout=20) as response:
        build = json.load(response)
    if build.get("build_sha", "").lower() != expected_sha or build.get("source_branch") != "main":
        raise AssertionError("Public deployment has not converged to EXPECTED_SHA on main")

    errors: list[str] = []
    request_payloads: list[dict] = []
    message = "Browser smoke - no live model call"
    fixture = "AYAHOS_BROWSER_SMOKE_OK"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))

        def mock_chat(route):
            request = route.request
            try:
                payload = request.post_data_json
                if request.method != "POST" or not isinstance(payload, dict):
                    raise AssertionError("Chat request was not a JSON POST")
                request_payloads.append(payload)
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"status": "completed", "text": fixture}),
                )
            except Exception as error:
                errors.append(str(error))
                route.fulfill(status=400, content_type="application/json", body='{"error":"mock failure"}')

        # Intercept before opening the page; no request reaches live /api/chat.
        page.route("**/api/chat", mock_chat)
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        composer = page.get_by_role("textbox", name="Message AyahOS")
        expect(composer).to_be_visible(timeout=15_000)
        expect(page.get_by_role("heading", name="What are we thinking through?")).to_be_visible()
        # Never contribute synthetic browser-test messages as learning evidence.
        learning = page.get_by_role("checkbox", name="Contribute text-free operational learning evidence")
        learning.uncheck()
        composer.fill(message)
        page.get_by_role("button", name="Send").click()
        expect(page.get_by_text(message, exact=True)).to_be_visible(timeout=10_000)
        expect(page.get_by_text(fixture, exact=True)).to_be_visible(timeout=10_000)
        assert len(request_payloads) == 1, "Expected exactly one intercepted chat request"
        payload = request_payloads[0]
        assert payload.get("learning_consent") is False
        assert payload.get("messages", [])[-1] == {"role": "user", "content": message}
        assert not errors, f"Browser errors: {errors}"
        context.close()
        browser.close()

    print(json.dumps({
        "result": "PASS",
        "scope": "deployed-browser-with-mocked-chat",
        "site": url,
        "build_sha": expected_sha,
        "live_inference_tested": False,
        "live_chat_requests_sent": 0,
    }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(json.dumps({"result": "FAIL", "reason": str(error)}), file=sys.stderr)
        sys.exit(1)
