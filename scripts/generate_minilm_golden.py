"""Generate the generator-derived MiniLM golden set + empirical baseline data.

This is the build-time companion to ``scripts/minilm_drift_check.py`` (the
gate itself stays stdlib-only and offline). It rebuilds the two data inputs
the gate's caveats used to lack:

* **Labeled golden cases.** The classifier's training set is synthetic: the
  artifact's ``training_metadata.dataset_fingerprint`` is reproduced exactly
  by ``dual_lineage.learning.synthetic.generate_synthetic_examples`` with
  the training seed (this script asserts the fingerprints match and refuses
  to run otherwise). One case per scenario family (144 families) is embedded
  with the pinned MiniLM model via the repo's own ``OnnxMiniLMEmbedder``
  and frozen into the golden file together with the generator's ground-truth
  labels and the current artifact's scores. Provenance is honest: these
  cases are derived from the training distribution's own generator, NOT
  from real traffic -- no labeled real-traffic dataset exists yet.
* **Empirical score distribution.** A deterministic stride sample of the
  same 12,000 generated examples (default every 10th -> 1,200 rows) is
  scored with the current artifact and written as a scores JSONL. The gate
  locks its per-head histograms into the baseline, which is what lets
  ``check --observed`` fail on real drift instead of only warning.

Requires the ML environment (``ml-requirements.txt``: onnxruntime,
transformers, huggingface-hub) and network access for the one-time model
download, or a cached snapshot via DUAL_LINEAGE_MINILM_LOCAL_PATH /
DUAL_LINEAGE_MINILM_ONNX_PATH. Output is deterministic: fixed generator
seed, fixed selection, embeddings and scores rounded to 6 decimals, so
re-running in the same environment produces byte-identical files.

Usage:
    PYTHONPATH=apps/api/src .venv/bin/python scripts/generate_minilm_golden.py
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from dual_lineage.brains.undermind.shadow import OnnxMiniLMEmbedder
from dual_lineage.learning.synthetic import generate_synthetic_examples
from dual_lineage.learning.training import dataset_fingerprint

DEFAULT_ARTIFACT = ROOT / "models" / "classifiers" / "minilm-shadow-v1.json"
DEFAULT_GOLDEN = ROOT / "benchmarks" / "datasets" / "golden" / "minilm-shadow-golden-v1.jsonl"
DEFAULT_EMPIRICAL = ROOT / "benchmarks" / "datasets" / "golden" / "minilm-shadow-empirical-v1.jsonl"
SCORE_FIELDS = {
    "complexity": "complexity_score",
    "risk": "risk_score",
    "uncertainty": "uncertainty_score",
    "escalation": "escalation_probability",
}


def _load_gate():
    spec = importlib.util.spec_from_file_location(
        "minilm_drift_check", ROOT / "scripts" / "minilm_drift_check.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _round6(values: list[float]) -> list[float]:
    return [round(float(v), 6) for v in values]


async def _embed(texts: list[str], revision: str | None) -> list[list[float]]:
    embedder = OnnxMiniLMEmbedder(revision=revision)
    vectors = await embedder.embed_many(texts)
    return [list(v) for v in vectors]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--empirical", type=Path, default=DEFAULT_EMPIRICAL)
    parser.add_argument("--count", type=int, default=12_000)
    parser.add_argument("--empirical-stride", type=int, default=10)
    args = parser.parse_args()

    gate = _load_gate()
    artifact = json.loads(args.artifact.read_text(encoding="utf-8"))
    errors = gate.validate_artifact(artifact)
    if errors:
        print(f"refusing to generate from an invalid artifact: {errors}", file=sys.stderr)
        return 1
    metadata = artifact.get("training_metadata") or {}
    seed = int(metadata.get("seed") or 20260927)
    expected_fingerprint = metadata.get("dataset_fingerprint")

    examples = generate_synthetic_examples(count=args.count, seed=seed)
    fingerprint = dataset_fingerprint(examples)
    if expected_fingerprint and fingerprint != expected_fingerprint:
        print(
            "dataset fingerprint mismatch: generator produced "
            f"{fingerprint}, artifact was trained on {expected_fingerprint}. "
            "The generator/seed no longer reproduces the training set; fix "
            "provenance before regenerating golden data.",
            file=sys.stderr,
        )
        return 1

    # Golden selection: first example (by sample_id) of every scenario
    # family -- deterministic and family-complete (all 144 families).
    by_family: dict[str, Any] = {}
    for example in sorted(examples, key=lambda e: e.sample_id):
        by_family.setdefault(example.scenario_family, example)
    golden_examples = [by_family[name] for name in sorted(by_family)]

    # Empirical selection: fixed stride over the generator's deterministic
    # (seeded, shuffled) output sequence.
    empirical_examples = list(examples[:: args.empirical_stride])

    unique = {e.sample_id: e for e in [*golden_examples, *empirical_examples]}
    ordered = [unique[key] for key in sorted(unique)]
    vectors = asyncio.run(
        _embed([e.prompt for e in ordered], artifact.get("embedding_revision"))
    )
    embeddings = {e.sample_id: v for e, v in zip(ordered, vectors)}

    def labels_of(example: Any) -> dict[str, Any]:
        return {
            "complexity": example.complexity_label,
            "risk": example.risk_label,
            "uncertainty": example.uncertainty_label,
            "escalation": example.escalation_label,
            "task_class": example.task_class.value,
        }

    def scores_of(example: Any) -> dict[str, Any]:
        return gate.score_embedding(artifact, embeddings[example.sample_id])

    # Empirical scores file (feeds the baseline's empirical distributions and
    # doubles as an --observed input with known-good drift ~ 0).
    empirical_lines = [
        json.dumps(
            {
                "probe_id": "__meta__",
                "kind": "empirical_scores_v1",
                "note": (
                    "Score distribution of the current artifact over a deterministic "
                    "stride sample of the synthetic training-distribution generator "
                    "(dual_lineage.learning.synthetic, seed = training seed). "
                    "Synthetic provenance: replace with captured shadow traffic once "
                    "a capture log exists. Not real traffic."
                ),
                "dataset_fingerprint": fingerprint,
                "generator_seed": seed,
                "generator_count": args.count,
                "stride": args.empirical_stride,
                "artifact_version": artifact["artifact_version"],
            },
            sort_keys=True,
        )
    ]
    for example in empirical_examples:
        scores = scores_of(example)
        empirical_lines.append(
            json.dumps(
                {
                    "sample_id": example.sample_id,
                    "scenario_family": example.scenario_family,
                    "labels": labels_of(example),
                    **{field: round(float(scores[head]), 6) for head, field in SCORE_FIELDS.items()},
                    "task_class": scores["task_class"],
                    "would_escalate": scores["would_escalate"],
                },
                sort_keys=True,
            )
        )
    args.empirical.parent.mkdir(parents=True, exist_ok=True)
    args.empirical.write_text("\n".join(empirical_lines) + "\n", encoding="utf-8")

    # Golden file: generator-derived labeled cases first, then the gate's
    # constructed probes (write_golden preserves the synthetic rows below
    # verbatim and regenerates the constructed section + meta).
    synthetic_lines = []
    for example in golden_examples:
        scores = scores_of(example)
        synthetic_lines.append(
            json.dumps(
                {
                    "probe_id": example.sample_id,
                    "kind": "synthetic_generator",
                    "scenario_family": example.scenario_family,
                    "prompt": example.prompt,
                    "labels": labels_of(example),
                    "embedding": _round6(embeddings[example.sample_id]),
                    "expected": {
                        **{h: round(float(scores[h]), 6) for h in gate.BINARY_HEADS},
                        "task_class": scores["task_class"],
                        "would_escalate": scores["would_escalate"],
                    },
                },
                sort_keys=True,
            )
        )
    args.golden.write_text("\n".join(synthetic_lines) + "\n", encoding="utf-8")
    probe_count = gate.write_golden(artifact, args.golden)

    print(
        json.dumps(
            {
                "gate": "minilm_golden_generate",
                "decision": "pass",
                "dataset_fingerprint": fingerprint,
                "golden_labeled_cases": len(golden_examples),
                "golden_constructed_probes": probe_count,
                "empirical_rows": len(empirical_examples),
                "golden": str(args.golden),
                "empirical": str(args.empirical),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
