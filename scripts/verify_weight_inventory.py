"""Verify that model artifacts have an explicit, checksum-backed ownership record."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = ROOT / "models" / "weight-inventory.json"
OWNERSHIP_STATES = {
    "first-party-trained",
    "first-party-trained-unattested",
    "first-party-owned",
    "third-party-licensed",
    "unverified-operator-supplied",
    "vendor-hosted-no-possession",
}
# Fields of docs/provenance/model-rights-attestation.template.md. Every one must be filled in, and
# the record must name the exact artifact checksum, before an entry may claim first-party-owned.
ATTESTATION_FIELDS = (
    "Asset identifier",
    "Exact filename/repository and revision",
    "SHA-256",
    "Rights holder legal name",
    "Claimant legal name/entity",
    "Basis of ownership",
    "Covered rights",
    "Training-data rights evidence reference",
    "Upstream/base-model obligations, if any",
    "Evidence reference or secure record ID",
    "Effective date",
    "Authorized signatory",
    "Verification date",
)
ATTESTATION_BASES = {
    "created-from-scratch",
    "written-assignment",
    "employment-or-contractor-agreement",
}
_FIELD_LINE = re.compile(r"^- ([^:]+):(.*)$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _repo_path(value: str) -> Path:
    path = (ROOT / value).resolve()
    if ROOT not in path.parents and path != ROOT:
        raise ValueError(f"path escapes repository: {value}")
    return path


def parse_attestation(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        match = _FIELD_LINE.match(line.strip())
        if match:
            fields[match.group(1).strip()] = match.group(2).strip().strip("`").strip()
    return fields


def attestation_errors(entry_id: str, entry: dict[str, Any], record: str) -> list[str]:
    """Check a rights attestation record against the inventory entry it is meant to cover."""
    fields = parse_attestation(record)
    errors = [
        f"{entry_id}: attestation field {name!r} is empty"
        for name in ATTESTATION_FIELDS
        if not fields.get(name)
    ]
    expected = {
        "Asset identifier": entry_id,
        "SHA-256": entry.get("sha256"),
        "Rights holder legal name": entry.get("rights_holder"),
    }
    for name, value in expected.items():
        if fields.get(name) and fields[name] != value:
            errors.append(f"{entry_id}: attestation {name!r} does not match the inventory")
    basis = fields.get("Basis of ownership")
    if basis and basis not in ATTESTATION_BASES:
        errors.append(f"{entry_id}: attestation basis {basis!r} is not an accepted basis")
    for name in ("Effective date", "Verification date"):
        value = fields.get(name)
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                errors.append(f"{entry_id}: attestation {name!r} is not a YYYY-MM-DD date")
    return errors


def _ownership_claim_errors(entry_id: str, entry: dict[str, Any]) -> list[str]:
    rights_holder = entry.get("rights_holder")
    if not isinstance(rights_holder, str) or not rights_holder.strip():
        return [f"{entry_id}: first-party-owned requires a named rights_holder"]
    if not entry.get("sha256"):
        return [f"{entry_id}: first-party-owned requires the attested artifact sha256"]
    evidence = entry.get("rights_evidence")
    if not isinstance(evidence, dict):
        return [f"{entry_id}: first-party-owned requires rights_evidence with an attestation record"]
    record = evidence.get("attestation")
    if not isinstance(record, str):
        return [f"{entry_id}: rights_evidence.attestation must name the attestation record"]
    record_path = _repo_path(record)
    if not record_path.is_file():
        return [f"{entry_id}: missing attestation record {record}"]
    if evidence.get("attestation_sha256") != _sha256(record_path):
        return [f"{entry_id}: rights_evidence.attestation_sha256 does not match {record}"]
    return attestation_errors(entry_id, entry, record_path.read_text(encoding="utf-8"))


def verify(
    inventory_path: Path = DEFAULT_INVENTORY,
    *,
    local_root: Path | None = None,
) -> list[str]:
    payload: dict[str, Any] = json.loads(inventory_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        return ["unsupported weight inventory schema"]
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        return ["weight inventory has no entries"]
    errors: list[str] = []
    declared_files: set[str] = set()
    ids: set[str] = set()
    for entry in entries:
        entry_id = entry.get("id")
        if not isinstance(entry_id, str) or not entry_id or entry_id in ids:
            errors.append(f"invalid or duplicate entry id: {entry_id!r}")
        ids.add(entry_id)
        if entry.get("ownership") not in OWNERSHIP_STATES:
            errors.append(f"{entry_id}: invalid ownership state")
        if entry.get("ownership") == "first-party-owned":
            errors.extend(_ownership_claim_errors(entry_id, entry))
        if (
            entry.get("ownership") == "first-party-trained-unattested"
            and entry.get("authority") != "shadow-only"
        ):
            errors.append(f"{entry_id}: unattested first-party weights must stay shadow-only")
        paths = entry.get("paths", [])
        if not isinstance(paths, list):
            errors.append(f"{entry_id}: paths must be a list")
            continue
        for raw_path in paths:
            if not isinstance(raw_path, str):
                errors.append(f"{entry_id}: non-string path")
                continue
            declared_files.add(raw_path.rstrip("/"))
            path = _repo_path(raw_path)
            if not path.exists() and entry.get("ownership") != "third-party-licensed":
                errors.append(f"{entry_id}: missing declared artifact {raw_path}")
        manifest = entry.get("manifest")
        if isinstance(manifest, str):
            declared_files.add(manifest)
            manifest_path = _repo_path(manifest)
            if not manifest_path.is_file():
                errors.append(f"{entry_id}: missing manifest {manifest}")
            elif entry.get("manifest_sha256") and _sha256(manifest_path) != entry["manifest_sha256"]:
                errors.append(f"{entry_id}: checksum mismatch for {manifest}")
        assets = entry.get("local_assets", [])
        if not isinstance(assets, list):
            errors.append(f"{entry_id}: local_assets must be a list")
        elif local_root is not None:
            for asset in assets:
                filename = asset.get("filename") if isinstance(asset, dict) else None
                expected = asset.get("sha256") if isinstance(asset, dict) else None
                if not isinstance(filename, str) or not isinstance(expected, str):
                    errors.append(f"{entry_id}: local asset requires filename and sha256")
                    continue
                path = (local_root / filename).resolve()
                if not path.is_file():
                    errors.append(f"{entry_id}: missing local asset {path}")
                elif _sha256(path) != expected:
                    errors.append(f"{entry_id}: local asset checksum mismatch for {filename}")
        sha256 = entry.get("sha256")
        if sha256 and len(paths) == 1 and isinstance(paths[0], str):
            path = _repo_path(paths[0])
            if path.is_file() and _sha256(path) != sha256:
                errors.append(f"{entry_id}: checksum mismatch for {paths[0]}")
    for path in (ROOT / "models").rglob("*"):
        if (
            not path.is_file()
            or "cache" in path.parts
            or path.name == "weight-inventory.json"
            or path.suffix not in {".json", ".safetensors", ".bin", ".gguf", ".onnx", ".pt", ".pth"}
        ):
            continue
        relative = path.relative_to(ROOT).as_posix()
        if relative not in declared_files:
            errors.append(f"unrecorded model artifact: {relative}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument(
        "--local-root",
        type=Path,
        help="Also verify local_assets against a local model directory.",
    )
    args = parser.parse_args()
    errors = verify(
        args.inventory.resolve(),
        local_root=args.local_root.resolve() if args.local_root else None,
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Weight inventory verified: ownership states and checksums are explicit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
