#!/usr/bin/env python3
"""Prepare a disposable Ruby RAG test overlay using verified HQ Core migrations.

The output is source compatibility material only, NOT a database test pass.
Run real PostgreSQL 16 + pgvector acceptance separately on a disposable DB.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("hq_release_check", ROOT / "verify-release-manifest.py")
assert SPEC and SPEC.loader
PREFLIGHT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREFLIGHT)
verify = PREFLIGHT.verify


def _deny_symlinks(path: Path, label: str) -> None:
    if path.is_symlink() or any(p.is_symlink() for p in path.rglob("*")):
        raise ValueError(label + " contains a symlink; overlay inputs must be regular source")


def prepare(manifest: Path, workspace: Path, output: Path) -> Path:
    """Copy only Ruby RAG tests, link verified Core SQL, and never touch either source."""
    verify(manifest, workspace)
    if output.exists() or output.is_symlink():
        raise ValueError("overlay destination already exists; refusing overwrite")
    if not output.parent.is_dir():
        raise ValueError("overlay destination parent is not a directory")
    source = workspace / "ayahos-workloads" / "apps" / "rag-ruby"
    core = workspace / "ayahos-core" / "apps" / "api"
    migrations = core / "src" / "dual_lineage" / "db" / "migrations"
    if not (source / "test" / "migrated_schema_test.rb").is_file():
        raise ValueError("RAG migration compatibility test source missing")
    if not migrations.is_dir() or not any(migrations.glob("*.sql")):
        raise ValueError("Core SQL migrations missing")
    _deny_symlinks(source, "RAG")
    _deny_symlinks(migrations, "Core SQL")
    if core.is_symlink():
        raise ValueError("Core API source is a symlink")
    base = workspace.resolve(strict=True)
    for part in (source, migrations, core):
        if not part.resolve(strict=True).is_relative_to(base):
            raise ValueError("HQ source escapes verified workspace")
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        (stage / "apps").mkdir()
        shutil.copytree(source, stage / "apps" / "rag-ruby", symlinks=False)
        # RAG's migrated_schema_test.rb uses ../../api/src/... from the Ruby
        # test directory. The overlay recreates that layout without copying,
        # modifying or maintaining another copy of SQL migration authority.
        (stage / "apps" / "api").symlink_to(core.resolve(strict=True),
                                              target_is_directory=True)
        data = {
            "schema_version": 1,
            "cutover_ready": False,
            "postgres16_pgvector_acceptance": "pending-real-integration-run",
            "migration_source": "ayahos-core",
            "rag_test_source": "ayahos-workloads",
        }
        (stage / "RAG-OVERLAY-EVIDENCE.json").write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )
        if output.exists() or output.is_symlink():
            raise ValueError("overlay destination appeared during copy")
        stage.rename(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return output


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, default=Path("release-manifest.json"))
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        output = prepare(args.manifest, args.workspace, args.output)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print("HQ RAG OVERLAY BLOCKED: " + str(exc), file=sys.stderr)
        return 1
    print("Prepared verified Core SQL + Ruby RAG test layout at " + str(output))
    print("No database integration or Octopus release has been verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
