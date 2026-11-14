#!/usr/bin/env python3
"""Read-only audit: does AyahOS's Cloudflare AI Gateway meet the $0 Jev policy?

Cloudflare's basic gateway is free, but this does NOT prove other AyahOS
providers, Workers AI on a paid plan, or electricity have zero cost.
Never echo credentials or provider response bodies.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping

GATEWAY_ID = "ayahos-undermind"
def validate(
    gateway: object, providers: object, topup: object,
) -> tuple[bool, tuple[str, ...]]:
    """Enforce the disabled paid-provider policy without spending anything."""
    errors: list[str] = []
    if not isinstance(gateway, Mapping):
        return False, ("gateway_missing",)
    required = {
        "id": GATEWAY_ID,
        "authentication": True,
        "byok_only": True,
        "collect_logs": False,
        "cache_ttl": 0,
        "zdr": True,
        "retry_max_attempts": 1,
    }
    for key, expected in required.items():
        if gateway.get(key) != expected:
            errors.append(f"gateway_{key}_unsafe")
    if not isinstance(providers, list):
        errors.append("provider_inventory_missing")
    else:
        matching = [p for p in providers if isinstance(p, Mapping) and p.get("slug") == "typesafe"]
        if len(matching) != 1 or matching[0].get("enable") is not False:
            errors.append("typesafe_must_be_disabled")
    if not isinstance(topup, Mapping) or topup.get("threshold") != 0 or topup.get("amount") != 0:
        errors.append("automatic_topup_must_be_disabled")
    # Workers AI is NOT protected by byok_only and gateway settings do not
    # establish the Workers Free plan. The integration MUST NOT call Workers AI.
    return not errors, tuple(errors)


def main() -> int:
    """Validate Ruby's read-only Cloudflare snapshot from standard input."""
    try:
        snapshot = json.load(sys.stdin)
        if not isinstance(snapshot, dict):
            raise ValueError("expected object")
        good, failures = validate(
            snapshot.get("gateway"),
            snapshot.get("providers"),
            snapshot.get("topup"),
        )
    except (ValueError, TypeError):
        print("Verification unavailable; invalid input snapshot.", file=sys.stderr)
        return 2
    if not good:
        print("Cloudflare $0 Jev gate FAILED: " + ",".join(failures), file=sys.stderr)
        return 1
    print("Cloudflare $0 Jev gate PASSED: TypeSafe disabled, no auto topup.")
    print("This check does NOT establish Workers AI billing eligibility.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
