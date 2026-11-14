#!/usr/bin/env python3
"""Provision the free AyahOS Cloudflare AI Gateway without enabling Jev traffic.

No new dependency; no provider credentials are stored or accessed. This tool
creates a locked-down gateway and a DISABLED custom TypeSafe provider, never
sends inference requests, and requires explicit --apply for account mutation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

GATEWAY_ID = "ayahos-undermind"
PROVIDER_SLUG = "typesafe"
PROVIDER_BASE = "https://api.typesafe.ai"
CF_API = "https://api.cloudflare.com/client/v4"


def _api(account_id: str, token: str, path: str, *, method: str = "GET",
         body: dict | None = None) -> object:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{CF_API}/accounts/{account_id}/ai-gateway/{path}",
        data=payload,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as res:
            response = json.load(res)
    except urllib.error.HTTPError as exc:
        # Never print Cloudflare's response: account or secret data may appear.
        location = path.split("?")[0]
        raise RuntimeError(
            f"Cloudflare API {method} {location} returned HTTP {exc.code}"
        ) from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("Cloudflare API request unavailable") from None
    if not isinstance(response, dict) or response.get("success") is not True:
        raise RuntimeError(f"Cloudflare API rejected {method} {path.split('?')[0]}")
    return response.get("result")


def provision(account_id: str, token: str, *, apply: bool) -> tuple[str, str]:
    if not re.fullmatch(r"[0-9a-f]{32}", account_id):
        raise ValueError("CLOUDFLARE_ACCOUNT_ID must be a 32-digit lowercase hex string")
    if not token.strip():
        raise ValueError("CLOUDFLARE_API_TOKEN must be nonempty")

    gateways = _api(account_id, token, "gateways")
    if not isinstance(gateways, list):
        raise RuntimeError("Unexpected gateway-list API response")
    found = next((g for g in gateways if isinstance(g, dict) and g.get("id") == GATEWAY_ID), None)
    if found:
        if found.get("authentication") is not True or found.get("byok_only") is not True:
            raise RuntimeError("Existing gateway lacks authenticated/BYOK-only protections; stop")
        gateway_status = "existing-locked"
    elif not apply:
        gateway_status = "would-create-free-locked"

    providers = _api(account_id, token, "custom-providers?search=typesafe")
    if not isinstance(providers, list):
        raise RuntimeError("Unexpected provider-list API response")
    provider = next((p for p in providers if isinstance(p, dict)
                     and p.get("slug") == PROVIDER_SLUG), None)
    if provider:
        if provider.get("base_url", "").rstrip("/") != PROVIDER_BASE:
            raise RuntimeError("Existing typesafe provider has different upstream; stop")
        if provider.get("enable") is True:
            raise RuntimeError("Existing typesafe provider is enabled; not safe in $0 setup")
        provider_status = "existing-disabled"
    elif not apply:
        provider_status = "would-create-disabled"

    # Both resources are fully validated before the first mutation. This
    # prevents a later provider conflict from leaving a half-provisioned
    # gateway behind.
    if apply:
        if not found:
            _api(account_id, token, "gateways", method="POST", body={
                "id": GATEWAY_ID,
                "cache_invalidate_on_update": True,
                "cache_ttl": 0,
                "collect_logs": False,
                "rate_limiting_interval": 60,
                "rate_limiting_limit": 10,
                "authentication": True,
                "byok_only": True,
                "zdr": True,
            })
            gateway_status = "created-locked"
        if not provider:
            _api(account_id, token, "custom-providers", method="POST", body={
                "name": "TypeSafe Jev (disabled - paid upstream)",
                "slug": PROVIDER_SLUG,
                "base_url": PROVIDER_BASE,
                "description": "Experimental AyahOS Undermind observer; no paid traffic authorized",
                "enable": False,
            })
            provider_status = "created-disabled"

    return gateway_status, provider_status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="Create missing free gateway and disabled custom provider")
    args = parser.parse_args()
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip().lower()
    token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    if not account_id or not token:
        print(
            "Required protected environment credentials unavailable; no changes made.",
            file=sys.stderr,
        )
        return 2
    try:
        gateway, provider = provision(account_id, token, apply=args.apply)
    except (RuntimeError, ValueError) as exc:
        print(f"Provisioning stopped: {exc}", file=sys.stderr)
        return 1
    print(f"Gateway: {gateway}; TypeSafe provider: {provider}; Jev calls: OFF")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
