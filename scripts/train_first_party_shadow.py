"""Train a self-contained first-party shadow classifier from repository data.

The generated artifact contains only the TF-IDF transform and linear heads
trained here. It deliberately has no downloaded encoder and remains
shadow-only; deterministic Undermind policy is still authoritative.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from dual_lineage.brains.undermind.shadow import (
    FirstPartyTextArtifact,
    LinearHead,
    ShadowTaskClass,
)
from dual_lineage.learning.synthetic import generate_synthetic_examples
from dual_lineage.learning.training import (
    MiniLMTrainingExample,
    split_by_scenario_family,
)
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "models" / "classifiers" / "first-party-shadow-v1.json"
SEED = 20261001


def _texts(examples: list[MiniLMTrainingExample]) -> list[str]:
    return [example.prompt for example in examples]


def _head(
    vectorizer: TfidfVectorizer,
    examples: list[MiniLMTrainingExample],
    labels: list[bool],
) -> LinearHead:
    matrix = vectorizer.transform(_texts(examples))
    model = LogisticRegression(
        class_weight="balanced",
        max_iter=300,
        random_state=SEED,
        solver="liblinear",
    )
    model.fit(matrix, labels)
    return LinearHead(
        weights=tuple(float(value) for value in model.coef_[0]),
        bias=float(model.intercept_[0]),
    )


def _task_heads(
    vectorizer: TfidfVectorizer,
    examples: list[MiniLMTrainingExample],
) -> dict[ShadowTaskClass, LinearHead]:
    matrix = vectorizer.transform(_texts(examples))
    labels = [example.task_class.value for example in examples]
    model = LogisticRegression(max_iter=300, random_state=SEED, solver="lbfgs")
    model.fit(matrix, labels)
    return {
        ShadowTaskClass(task): LinearHead(
            weights=tuple(float(value) for value in row),
            bias=float(bias),
        )
        for task, row, bias in zip(model.classes_, model.coef_, model.intercept_)
    }


def _fingerprint(examples: list[MiniLMTrainingExample]) -> str:
    payload = "\n".join(example.model_dump_json() for example in examples)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def train(output: Path, *, count: int = 12_000) -> dict[str, object]:
    all_examples = list(generate_synthetic_examples(count=count, seed=SEED))
    split = split_by_scenario_family(all_examples, seed=SEED)
    train_examples = list(split.train)
    calibration_examples = list(split.calibration)
    test_examples = list(split.test)
    vectorizer = TfidfVectorizer(
        lowercase=True,
        ngram_range=(1, 2),
        norm="l2",
        sublinear_tf=True,
        token_pattern=r"(?u)\b[\w.-]+\b",
        max_features=512,
    )
    vectorizer.fit(_texts(train_examples))
    vocabulary = {term: int(index) for term, index in vectorizer.vocabulary_.items()}
    idf = tuple(float(value) for value in vectorizer.idf_)
    artifact = FirstPartyTextArtifact(
        artifact_version="first-party-shadow-v1",
        vocabulary=vocabulary,
        idf=idf,
        complexity=_head(vectorizer, train_examples, [item.complexity_label for item in train_examples]),
        risk=_head(vectorizer, train_examples, [item.risk_label for item in train_examples]),
        uncertainty=_head(vectorizer, train_examples, [item.uncertainty_label for item in train_examples]),
        escalation=_head(vectorizer, train_examples, [item.escalation_label for item in train_examples]),
        task_classes=_task_heads(vectorizer, train_examples),
        training_metadata={
            "ownership": "first-party-trained-unattested",
            "evidence_source": "repository-generated-synthetic",
            "dataset_fingerprint": _fingerprint(all_examples),
            "seed": SEED,
            "train_count": len(train_examples),
            "calibration_count": len(calibration_examples),
            "test_count": len(test_examples),
            "train_families": list(split.train_families),
            "calibration_families": list(split.calibration_families),
            "test_families": list(split.test_families),
            "encoder": "none",
            "rights_evidence": "docs/provenance/model-rights-attestation.template.md",
        },
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(artifact.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "artifact": output.as_posix(),
        "features": len(vocabulary),
        "train": len(train_examples),
        "test": len(test_examples),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "ownership": artifact.training_metadata["ownership"],
    }, indent=2))
    return artifact.model_dump()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--count", type=int, default=12_000)
    args = parser.parse_args()
    train(args.output.resolve(), count=args.count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
