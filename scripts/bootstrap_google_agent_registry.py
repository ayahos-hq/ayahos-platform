"""Plan or explicitly apply least-privilege Agent Registry IAM bootstrap.

The default is dry-run. This script never creates service-account keys.
"""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Sequence

VIEWER = "ayahos-agent-registry-viewer"
PUBLISHER = "ayahos-agent-registry-publisher"


def commands(project: str) -> tuple[tuple[str, ...], ...]:
    viewer = f"{VIEWER}@{project}.iam.gserviceaccount.com"
    publisher = f"{PUBLISHER}@{project}.iam.gserviceaccount.com"
    return (
        ("gcloud", "iam", "service-accounts", "create", VIEWER, "--project", project),
        ("gcloud", "iam", "service-accounts", "create", PUBLISHER, "--project", project),
        (
            "gcloud",
            "projects",
            "add-iam-policy-binding",
            project,
            "--member",
            f"serviceAccount:{viewer}",
            "--role",
            "roles/agentregistry.viewer",
        ),
        (
            "gcloud",
            "projects",
            "add-iam-policy-binding",
            project,
            "--member",
            f"serviceAccount:{publisher}",
            "--role",
            "roles/agentregistry.editor",
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--apply", action="store_true", help="mutate IAM; dry-run is the default")
    args = parser.parse_args(argv)
    planned = commands(args.project)
    for command in planned:
        print(" ".join(command))
    if not args.apply:
        print("dry-run only; no IAM changes made")
        return 0
    for command in planned:
        subprocess.run(command, check=True)
    print("IAM bootstrap applied; no service-account keys were created")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
