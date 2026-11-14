#!/usr/bin/env python3
"""Fail-closed post-deploy test of REAL public AyahOS JSON and SSE inference.

Stdlib only, no API key: exercises Cloudflare -> Fly -> permitted model route.
Use after the public site converges to EXPECTED_SHA; never against a PR preview.
No prompts/responses/credentials are written to evidence. Invocations cost two
bounded model requests, so run once per deployment rather than on every CI push.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

MAX_BYTES = 256 * 1024
TIMEOUT_SECONDS = 30


def validate_expected_sha(value: str) -> str:
    sha = value.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("EXPECTED_SHA must be the full deployed 40-character commit SHA")
    return sha


def validate_site_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or parsed.scheme not in ("http", "https")
        or (parsed.scheme != "https" and parsed.hostname not in ("127.0.0.1", "localhost"))
    ):
        raise ValueError("LIVE_PUBLIC_SITE_URL must be a credential-free HTTPS origin")
    return value.rstrip("/")


def verify_build(body: object, expected_sha: str) -> None:
    assert isinstance(body, dict), "build response was not JSON object"
    assert body.get("source_branch") == "main", "deployed source branch is not main"
    assert body.get("build_sha", "").lower() == expected_sha, "deployed SHA mismatch"


def verify_json(body: object) -> str:
    assert isinstance(body, dict), "JSON chat response was not object"
    assert body.get("status") == "completed", "JSON chat did not complete"
    assert isinstance(body.get("text"), str) and body["text"].strip(), "JSON chat returned empty text"
    provider = body.get("provider")
    assert isinstance(provider, str) and provider.strip() and provider != "public-knowledge", "JSON chat did not use a model provider"
    return provider


def verify_sse(raw: bytes) -> int:
    assert len(raw) <= MAX_BYTES, "stream exceeded bounded evidence read"
    text = raw.decode("utf-8", errors="strict").replace("\r\n", "\n")
    started = False
    delta_count = 0
    completed = False
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        event = ""
        data: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].lstrip())
        if not event:
            continue
        try:
            payload = json.loads("\n".join(data))
        except (json.JSONDecodeError, ValueError) as exc:
            raise AssertionError("SSE event contained invalid JSON") from exc
        assert isinstance(payload, dict), "SSE event data is not a JSON object"
        assert not completed, "SSE contained data after terminal event"
        if event == "error":
            raise AssertionError("SSE returned error event")
        if event == "start":
            started = True
        elif event == "delta" and isinstance(payload.get("text"), str) and payload["text"].strip():
            delta_count += 1
        elif event == "done":
            assert payload.get("status") == "completed", "SSE ended without completed status"
            completed = True
    assert started, "SSE never started"
    assert delta_count > 0, "SSE contained no model text"
    assert completed, "SSE ended without terminal done event"
    return delta_count


def fetch(url: str, *, body: dict | None = None, accept: str = "application/json") -> tuple[int, str, bytes]:
    data = json.dumps(body, separators=(",", ":")).encode() if body is not None else None
    headers = {"Accept": accept, "User-Agent": "AyahOS-live-chat-gate/1", "Cache-Control": "no-cache"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, headers=headers, data=data, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise AssertionError("response exceeded bounded evidence read")
        return response.status, response.headers.get("Content-Type", "").lower(), raw


def main() -> int:
    started = time.monotonic()
    evidence = {
        "source": "live_chat_gate",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "decision": "HOLD",
        "checks": [],
    }
    output = Path(os.environ.get("LIVE_CHAT_GATE_OUTPUT", "artifacts/live-chat-gate.json"))
    try:
        expected = validate_expected_sha(os.environ.get("EXPECTED_SHA", ""))
        site = validate_site_url(os.environ.get("LIVE_PUBLIC_SITE_URL", "https://ayahos.pages.dev"))
        evidence["expected_site_sha"] = expected
        evidence["site"] = site

        def check(name, func):
            before = time.monotonic()
            result = func()
            evidence["checks"].append({"check": name, "passed": True, "latency_ms": int((time.monotonic() - before) * 1000), **result})

        def build_check():
            code, ct, raw = fetch(site + "/api/build")
            assert code == 200 and "application/json" in ct, "build endpoint status/content type invalid"
            verify_build(json.loads(raw), expected)
            return {}

        def json_check():
            code, ct, raw = fetch(site + "/api/chat", body={"messages": [{"role": "user", "content": "Reply with one word: OK."}]})
            assert code == 200 and "application/json" in ct, "chat JSON endpoint status/content type invalid"
            return {"provider": verify_json(json.loads(raw))}

        def stream_check():
            code, ct, raw = fetch(site + "/api/chat", body={"messages": [{"role": "user", "content": "Reply with one word: STREAM_OK."}], "stream": True}, accept="text/event-stream")
            assert code == 200 and "text/event-stream" in ct, "chat SSE endpoint status/content type invalid"
            return {"nonempty_delta_events": verify_sse(raw)}

        check("public_build_sha", build_check)
        check("public_chat_json", json_check)
        check("public_chat_sse", stream_check)
        evidence["decision"] = "PASS"
    except (AssertionError, ValueError, OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        evidence["checks"].append({"check": "blocked", "passed": False, "reason": type(exc).__name__ + ": " + str(exc)[:180]})
    finally:
        evidence["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(evidence, separators=(",", ":")))
    return 0 if evidence["decision"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
