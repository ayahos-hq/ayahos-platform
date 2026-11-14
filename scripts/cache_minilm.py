"""Download a pinned MiniLM snapshot and emit reproducibility metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from huggingface_hub import model_info, snapshot_download

DEFAULT_REPO = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
FULL_MODEL_PATTERNS = (
    "*.json",
    "*.txt",
    "*.safetensors",
    "1_Pooling/*",
)
ONNX_MODEL_PATTERNS = (
    "*.json",
    "*.txt",
    "tokenizer*",
    "vocab.txt",
    "1_Pooling/*",
    "onnx/model.onnx",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _license_name(card_data: object) -> str | None:
    value = getattr(card_data, "license", None)
    if isinstance(value, str):
        return value
    if isinstance(card_data, dict):
        raw = card_data.get("license")
        return raw if isinstance(raw, str) else None
    return None


def cache_model(
    *,
    repo_id: str,
    revision: str,
    output_dir: Path,
    manifest_path: Path,
    patterns: tuple[str, ...] = FULL_MODEL_PATTERNS,
) -> Path:
    info = model_info(repo_id, revision=revision)
    resolved_revision = str(info.sha or revision)
    snapshot = Path(
        snapshot_download(
            repo_id=repo_id,
            revision=revision,
            local_dir=output_dir,
            allow_patterns=list(patterns),
        )
    )

    files: list[dict[str, object]] = []
    total_bytes = 0
    for path in sorted(snapshot.rglob("*")):
        if not path.is_file() or ".cache" in path.parts:
            continue
        size = path.stat().st_size
        total_bytes += size
        files.append(
            {
                "path": path.relative_to(snapshot).as_posix(),
                "bytes": size,
                "sha256": _sha256(path),
            }
        )

    manifest = {
        "repo_id": repo_id,
        "requested_revision": revision,
        "resolved_revision": resolved_revision,
        "license": _license_name(info.card_data),
        "embedding_dim": 384,
        "download_patterns": list(patterns),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "files": files,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"cached={snapshot}")
    print(f"manifest={manifest_path}")
    print(f"resolved_revision={resolved_revision}")
    print(f"files={len(files)} bytes={total_bytes}")
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-id", default=DEFAULT_REPO)
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--profile", choices=("full", "onnx"), default="full")
    args = parser.parse_args()
    patterns = ONNX_MODEL_PATTERNS if args.profile == "onnx" else FULL_MODEL_PATTERNS
    cache_model(
        repo_id=args.repo_id,
        revision=args.revision,
        output_dir=Path(args.output_dir),
        manifest_path=Path(args.manifest),
        patterns=patterns,
    )


if __name__ == "__main__":
    main()

