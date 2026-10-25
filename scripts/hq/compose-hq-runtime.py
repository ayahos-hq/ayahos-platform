#!/usr/bin/env python3
"""Compose the reviewed Core + Workloads candidate runtime context.

This is source composition only. It does not build, push, deploy, authorize,
or promote an image. The resulting context keeps Python as the only action
authority and packages Ruby only as bounded transport/workflow/RAG support.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
SPEC = importlib.util.spec_from_file_location("hq_source_preflight", SCRIPTS / "verify-release-manifest.py")
if not SPEC or not SPEC.loader:
    raise RuntimeError("release manifest verifier is unavailable")
PREFLIGHT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREFLIGHT)

REPOSITORIES = dict(PREFLIGHT.REPOSITORIES)
SHA = re.compile(r"\A[0-9a-f]{40}\Z")
SELECTED_PATHS = {
    "ayahos-core": ("apps/api",),
    "ayahos-workloads": ("apps/rag-ruby", "apps/control-ruby", "apps/ruby_worker"),
}
DOCKERFILE = HERE / "Dockerfile.hq-composite"
STARTUP = HERE / "start-hq-composite.sh"
DOCKERFILE_NAME = "Dockerfile"
STARTUP_NAME = "scripts/start-hq-composite.sh"
PROVENANCE_NAME = "COMPOSITE-SOURCE-MANIFEST.json"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git_head(checkout: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()


def reject_unsafe_tree(source: Path, label: str) -> None:
    if source.is_symlink() or not source.is_dir():
        raise ValueError(f"required source directory is missing or unsafe: {label}")
    for path in sorted(source.rglob("*"), key=lambda item: item.relative_to(source).as_posix()):
        if path.is_symlink():
            raise ValueError(f"symlink is forbidden in composite source: {label}/{path.relative_to(source)}")
        if not path.is_dir() and not path.is_file():
            raise ValueError(f"special file is forbidden in composite source: {label}/{path.relative_to(source)}")


def copy_tree_without_collisions(source: Path, destination: Path, label: str) -> None:
    reject_unsafe_tree(source, label)
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"composite path collision: {destination}")
    destination.mkdir(parents=True)
    entries = sorted(
        source.rglob("*"),
        key=lambda item: (not item.is_dir(), item.relative_to(source).as_posix()),
    )
    for path in entries:
        relative = path.relative_to(source)
        target = destination / relative
        if target.exists() or target.is_symlink():
            raise ValueError(f"composite path collision: {target}")
        if path.is_dir():
            target.mkdir()
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        else:
            raise ValueError(f"special file is forbidden in composite source: {label}/{relative}")


def copy_file_without_collision(source: Path, destination: Path, label: str) -> None:
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"required file is missing or unsafe: {label}")
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"composite path collision: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def expected_checkouts(manifest: dict, receipt: dict) -> dict[str, str]:
    components = manifest.get("components")
    if not isinstance(components, dict) or set(components) != set(REPOSITORIES):
        raise ValueError("manifest must contain exactly the five HQ repositories")
    checkout_shas = receipt.get("component_checkout_shas")
    platform_head = receipt.get("platform_checkout_sha")
    if not isinstance(checkout_shas, dict) or set(checkout_shas) != set(REPOSITORIES):
        raise ValueError("candidate receipt must name exactly five checkouts")
    if not isinstance(platform_head, str) or not SHA.fullmatch(platform_head):
        raise ValueError("candidate receipt has an invalid platform checkout SHA")

    expected = {}
    for name in REPOSITORIES:
        if name == "ayahos-platform":
            expected[name] = platform_head
        else:
            expected[name] = components[name]["git_sha"]
        if checkout_shas.get(name) != expected[name] or not SHA.fullmatch(expected[name]):
            raise ValueError(f"candidate receipt SHA mismatch: {name}")
    return expected


def compose(manifest_path: Path, workspace: Path, destination: Path) -> Path:
    if destination.exists() or destination.is_symlink():
        raise ValueError("composite context destination already exists")
    if not destination.parent.is_dir():
        raise ValueError("composite context parent is missing")
    if workspace.is_symlink() or not workspace.is_dir():
        raise ValueError("composite workspace is missing or unsafe")
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("candidate manifest is missing or unsafe")

    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    receipt_path = workspace / "CANDIDATE-SOURCE-EVIDENCE.json"
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise ValueError("candidate source receipt is missing or unsafe")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    # Re-run the authoritative offline source verifier before copying any code.
    PREFLIGHT.verify(manifest_path, workspace)
    expected = expected_checkouts(manifest, receipt)
    platform_manifest = workspace / "ayahos-platform" / "release-manifest.json"
    if platform_manifest.is_symlink() or platform_manifest.read_bytes() != manifest_bytes:
        raise ValueError("platform checkout manifest differs from requested candidate")

    for name, revision in expected.items():
        checkout = workspace / name
        actual = git_head(checkout)
        if actual != revision:
            raise ValueError(f"composite checkout HEAD mismatch: {name}")
        reject_unsafe_tree(checkout, name)

    if not DOCKERFILE.is_file() or DOCKERFILE.is_symlink():
        raise ValueError("reviewed composite Dockerfile is missing")
    if not STARTUP.is_file() or STARTUP.is_symlink():
        raise ValueError("reviewed composite startup script is missing")

    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        for repository, paths in SELECTED_PATHS.items():
            for relative in paths:
                source = workspace / repository / relative
                copy_tree_without_collisions(source, staging / relative, f"{repository}/{relative}")

        copy_file_without_collision(DOCKERFILE, staging / DOCKERFILE_NAME, "platform composite Dockerfile")
        copy_file_without_collision(STARTUP, staging / STARTUP_NAME, "platform composite startup")
        (staging / STARTUP_NAME).chmod(0o755)

        component_pins = {
            name: manifest["components"][name]["git_sha"] for name in REPOSITORIES
        }
        source_manifest = {
            "schema_version": 1,
            "candidate_only": True,
            "release_id": manifest.get("release_id"),
            "release_manifest_sha256": sha256_bytes(manifest_bytes),
            "manifest_component_pins": component_pins,
            "checkout_shas": expected,
            "included_paths": {
                "ayahos-core": ["apps/api"],
                "ayahos-workloads": [
                    "apps/rag-ruby",
                    "apps/control-ruby",
                    "apps/ruby_worker",
                ],
            },
            "authority_contract": {
                "python_authority": [
                    "deterministic_undermind",
                    "authorization",
                    "quota_admission",
                    "routing_decision",
                    "interrupts",
                    "action_gateway",
                    "shared_spine",
                ],
                "ruby_bounded_support": ["transport", "workflow", "rag"],
                "provider_calls_allowed_in": ["ayahos-core"],
                "provider_calls_forbidden_in": [
                    "ayahos-site",
                    "ayahos-admin",
                    "ayahos-workloads",
                ],
                "inference_provider_gateway_and_action_gateway_are_distinct": True,
                "duplicate_authorities_forbidden": True,
                "rag_corpora": {
                    "overmind": "rag",
                    "advisory_undermind": "undermind_rag",
                    "external_text_is_untrusted_data": True,
                },
            },
            "runtime_contract": {
                "public_process": "FastAPI dual_lineage.main:app",
                "public_port": 8000,
                "internal_rag_port": 8102,
                "internal_control_port": 8103,
                "worker_role": "Ruby bounded workflow worker",
                "startup_migrations": False,
                "acceptance": "pending-independent-build-and-runtime-gates",
            },
        }
        (staging / PROVENANCE_NAME).write_text(
            json.dumps(source_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if destination.exists() or destination.is_symlink():
            raise ValueError("composite context destination appeared during assembly")
        staging.rename(destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("release-manifest.json"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = compose(args.manifest, args.workspace, args.output)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print("HQ COMPOSITE CONTEXT BLOCKED: " + str(exc), file=sys.stderr)
        return 1
    print("Composed verified Core + Workloads source context at " + str(result))
    print("No image build, provider call, deployment, or release authorization was performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
