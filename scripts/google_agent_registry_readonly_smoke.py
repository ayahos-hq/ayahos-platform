"""Run a bounded, read-only Google Agent Registry inventory check."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from typing import Any


def _run(command: list[str]) -> str:
    executable = "gcloud.cmd" if sys.platform == "win32" else "gcloud"
    resolved = shutil.which(executable)
    if resolved is None:
        raise FileNotFoundError("gcloud CLI executable was not found")
    command[0] = resolved
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", default="global")
    parser.add_argument("--search-string", default="ayahos")
    args = parser.parse_args()
    raw = _run(
        [
            "gcloud",
            "agent-registry",
            "agents",
            "search",
            f"--project={args.project}",
            f"--location={args.location}",
            f"--search-string={args.search_string}",
            "--format=json",
        ]
    )
    document: Any = json.loads(raw)
    if not isinstance(document, dict):
        raise TypeError("registry response was not an object")
    agents = document.get("agents", [])
    if not isinstance(agents, list):
        raise TypeError("registry response contained an invalid agents field")
    identifiers = sorted(
        str(item.get("name", ""))
        for item in agents
        if isinstance(item, dict) and item.get("name")
    )
    print(f"registry readonly smoke: project={args.project} location={args.location}")
    print(f"inventory_count={len(agents)}")
    for identifier in identifiers:
        print(f"agent={identifier[:256]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
