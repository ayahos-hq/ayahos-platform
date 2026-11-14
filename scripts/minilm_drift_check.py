"""Drift-prevention gate for the MiniLM shadow classifier artifact.

Stdlib-only, offline. Implements the drift controls in
``docs/operations/minilm-drift-prevention.md`` for
``models/classifiers/minilm-shadow-v1.json``:

1. Baseline lock -- ``baseline`` writes a versioned baseline (artifact SHA-256,
   embedding model/revision, per-head weight stats and hashes, golden-probe
   score distributions). ``check`` fails if the live artifact differs from
   the locked baseline.
2. Input validation -- ``validate_artifact`` rejects malformed artifacts
   (wrong head dimension, non-finite weights, out-of-range threshold,
   unknown calibration method, missing/extra task classes) before any
   scoring happens. Probe embeddings and observed score rows are validated
   the same way.
3. Distribution monitoring -- ``check`` recomputes the golden-probe score
   distributions with the live artifact and reports PSI and KL divergence
   against the baseline histograms (pass < 0.10, warn < 0.25, fail >= 0.25).
   ``--observed scores.jsonl`` additionally compares recorded shadow scores
   against the baseline's *empirical* score distribution (the current
   artifact scored over a 1,200-case deterministic sample of the synthetic
   training-distribution generator, locked by
   ``scripts/generate_minilm_golden.py``); that mode FAILS at the same
   PSI/KL thresholds. Only a baseline that predates the empirical section
   falls back to the old probe comparison, still capped at ``warn``.
4. Golden eval -- a frozen set
   (``benchmarks/datasets/golden/minilm-shadow-golden-v1.jsonl``) with the
   scores the locked artifact produced. Most cases are derived from the
   classifier's own training-distribution generator
   (``dual_lineage.learning.synthetic``; the artifact's dataset
   fingerprint is reproduced and asserted at generation time) and carry
   the generator's ground-truth labels: ``check`` fails if any recomputed
   score moves beyond tolerance, any task/escalation decision flips, or
   label agreement drops more than the locked tolerance below the
   baseline agreement. The remaining cases are the original constructed
   seed probes (head-direction / basis / Gaussian vectors), kept because
   they cover embedding-space extremes no generated text reaches.
6. Shadow/canary comparison -- ``compare --candidate other.json`` scores the
   golden probes with a candidate artifact side by side with the current
   one and fails on decision flips or large score movement. A candidate is
   never promoted by this gate; it only reports the diff.
8. Human-review sampling -- ``sample predictions.jsonl`` deterministically
   picks the cases a human should eyeball first: near-threshold escalations
   and high-uncertainty predictions, plus a seeded random remainder.

Usage:
    python scripts/minilm_drift_check.py                 # check (default)
    python scripts/minilm_drift_check.py check --observed scores.jsonl
    python scripts/minilm_drift_check.py golden          # regenerate probes
    python scripts/minilm_drift_check.py baseline        # lock a new baseline
    python scripts/minilm_drift_check.py compare --candidate candidate.json
    python scripts/minilm_drift_check.py sample preds.jsonl --sample-size 50

Exit code is 0 for pass/warn and 1 for fail. Evidence is printed as JSON and
optionally written with ``--output`` (or ``MINILM_DRIFT_OUTPUT``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT = ROOT / "models" / "classifiers" / "minilm-shadow-v1.json"
DEFAULT_BASELINE = ROOT / "benchmarks" / "datasets" / "golden" / "minilm-shadow-v1.baseline.json"
DEFAULT_GOLDEN = ROOT / "benchmarks" / "datasets" / "golden" / "minilm-shadow-golden-v1.jsonl"
DEFAULT_EMPIRICAL = (
    ROOT / "benchmarks" / "datasets" / "golden" / "minilm-shadow-empirical-v1.jsonl"
)

BINARY_HEADS = ("complexity", "risk", "uncertainty", "escalation")
TASK_CLASSES = ("general", "analysis", "coding", "tool_use")
CALIBRATION_METHODS = {"platt", "none"}
SCORE_FIELDS = {
    "complexity": "complexity_score",
    "risk": "risk_score",
    "uncertainty": "uncertainty_score",
    "escalation": "escalation_probability",
}

PSI_WARN = 0.10
PSI_FAIL = 0.25
KL_WARN = 0.10
KL_FAIL = 0.25
GOLDEN_SCORE_TOLERANCE = 0.02
LABEL_AGREEMENT_TOLERANCE = 0.05
COMPARE_WARN_DELTA = 0.02
COMPARE_FAIL_DELTA = 0.10
HISTOGRAM_BINS = 10
_EPS = 1e-4
PROBE_SEED = 20261021


# ---------------------------------------------------------------------------
# Artifact validation (control 2) and scoring primitives
# ---------------------------------------------------------------------------


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _validate_head(name: str, head: Any, dim: int, errors: list[str]) -> None:
    if not isinstance(head, dict):
        errors.append(f"{name}: head must be an object")
        return
    weights = head.get("weights")
    if not isinstance(weights, list) or len(weights) != dim:
        errors.append(f"{name}: weights must be a list of length {dim}")
    elif not all(_is_finite_number(w) for w in weights):
        errors.append(f"{name}: weights must all be finite numbers")
    for field in ("bias", "calibration_scale", "calibration_bias"):
        if not _is_finite_number(head.get(field)):
            errors.append(f"{name}: {field} must be a finite number")
    if _is_finite_number(head.get("calibration_scale")) and head["calibration_scale"] == 0:
        errors.append(f"{name}: calibration_scale must be non-zero")
    if head.get("calibration_method") not in CALIBRATION_METHODS:
        errors.append(f"{name}: unsupported calibration_method {head.get('calibration_method')!r}")


def validate_artifact(artifact: Any) -> list[str]:
    """Return structural errors for a MiniLM shadow artifact (empty = valid)."""
    errors: list[str] = []
    if not isinstance(artifact, dict):
        return ["artifact must be a JSON object"]
    if not isinstance(artifact.get("artifact_version"), str) or not artifact["artifact_version"]:
        errors.append("artifact_version must be a non-empty string")
    if not isinstance(artifact.get("embedding_model"), str) or not artifact["embedding_model"]:
        errors.append("embedding_model must be a non-empty string")
    revision = artifact.get("embedding_revision")
    if revision is not None and not (
        isinstance(revision, str)
        and len(revision) == 40
        and all(c in "0123456789abcdef" for c in revision)
    ):
        errors.append("embedding_revision must be null or a 40-char lowercase hex revision")
    dim = artifact.get("embedding_dim")
    if not isinstance(dim, int) or isinstance(dim, bool) or dim <= 0:
        errors.append("embedding_dim must be a positive integer")
        return errors
    threshold = artifact.get("escalation_threshold")
    if not _is_finite_number(threshold) or not 0.0 < float(threshold) < 1.0:
        errors.append("escalation_threshold must be a finite number in (0, 1)")
    for name in BINARY_HEADS:
        _validate_head(name, artifact.get(name), dim, errors)
    task_classes = artifact.get("task_classes")
    if not isinstance(task_classes, dict):
        errors.append("task_classes must be an object")
    else:
        if set(task_classes) != set(TASK_CLASSES):
            errors.append(
                f"task_classes must be exactly {sorted(TASK_CLASSES)}, got {sorted(task_classes)}"
            )
        for name in TASK_CLASSES:
            if name in task_classes:
                _validate_head(f"task_classes.{name}", task_classes[name], dim, errors)
    return errors


def validate_embedding(embedding: Any, dim: int) -> list[str]:
    if not isinstance(embedding, list) or len(embedding) != dim:
        return [f"embedding must be a list of length {dim}"]
    if not all(_is_finite_number(v) for v in embedding):
        return ["embedding values must all be finite numbers"]
    return []


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    z = math.exp(value)
    return z / (1.0 + z)


def head_probability(head: dict[str, Any], embedding: list[float]) -> float:
    logit = sum(w * v for w, v in zip(head["weights"], embedding)) + head["bias"]
    calibrated = head["calibration_scale"] * logit + head["calibration_bias"]
    return _sigmoid(calibrated)


def head_logit(head: dict[str, Any], embedding: list[float]) -> float:
    return sum(w * v for w, v in zip(head["weights"], embedding)) + head["bias"]


def score_embedding(artifact: dict[str, Any], embedding: list[float]) -> dict[str, Any]:
    """Mirror MiniLMShadowClassifier.predict for one embedding (stdlib only)."""
    scores = {name: head_probability(artifact[name], embedding) for name in BINARY_HEADS}
    task_logits = {
        name: head_logit(artifact["task_classes"][name], embedding) for name in TASK_CLASSES
    }
    task_class = max(task_logits.items(), key=lambda item: item[1])[0]
    return {
        **scores,
        "task_class": task_class,
        "would_escalate": scores["escalation"] >= artifact["escalation_threshold"],
    }


# ---------------------------------------------------------------------------
# Statistics: histograms, PSI, KL (control 3)
# ---------------------------------------------------------------------------


def histogram(values: list[float], bins: int = HISTOGRAM_BINS) -> list[int]:
    counts = [0] * bins
    for value in values:
        index = min(bins - 1, max(0, int(value * bins)))
        counts[index] += 1
    return counts


def _proportions(counts: list[int]) -> list[float]:
    total = sum(counts) or 1
    return [max(count / total, _EPS) for count in counts]


def population_stability_index(expected: list[int], actual: list[int]) -> float:
    p, q = _proportions(expected), _proportions(actual)
    return sum((a - e) * math.log(a / e) for e, a in zip(p, q))


def kl_divergence(expected: list[int], actual: list[int]) -> float:
    p, q = _proportions(expected), _proportions(actual)
    return sum(a * math.log(a / e) for e, a in zip(p, q))


def _distribution(values: list[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "stdev": statistics.pstdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
        "histogram": histogram(values),
    }


def _drift_level(psi: float, kl: float) -> str:
    if psi >= PSI_FAIL or kl >= KL_FAIL:
        return "fail"
    if psi >= PSI_WARN or kl >= KL_WARN:
        return "warn"
    return "pass"


# ---------------------------------------------------------------------------
# Baseline lock (control 1) and golden probes (control 4)
# ---------------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _weights_sha256(weights: list[float]) -> str:
    canonical = json.dumps(weights, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _head_summary(head: dict[str, Any]) -> dict[str, Any]:
    weights = [float(w) for w in head["weights"]]
    return {
        "bias": head["bias"],
        "calibration_scale": head["calibration_scale"],
        "calibration_bias": head["calibration_bias"],
        "calibration_method": head["calibration_method"],
        "weights_sha256": _weights_sha256(weights),
        "weight_mean": statistics.fmean(weights),
        "weight_stdev": statistics.pstdev(weights),
        "weight_min": min(weights),
        "weight_max": max(weights),
        "weight_l2_norm": math.sqrt(sum(w * w for w in weights)),
    }


def generate_probes(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    """Deterministic probe embeddings, frozen into the golden file.

    Seed cases constructed from the classifier's documented behavior (the
    heads in shadow.py): the zero embedding, +/- the unit direction of every
    head (max/min response directions), single-axis basis vectors, and
    seeded Gaussian vectors (plus 2x-scaled stress variants). They are NOT
    recorded live traffic and NOT training data.
    """
    dim = artifact["embedding_dim"]
    probes: list[tuple[str, str, list[float]]] = [("zero", "zero", [0.0] * dim)]
    heads = [(name, artifact[name]) for name in BINARY_HEADS] + [
        (f"task:{name}", artifact["task_classes"][name]) for name in TASK_CLASSES
    ]
    for name, head in heads:
        weights = [float(w) for w in head["weights"]]
        norm = math.sqrt(sum(w * w for w in weights)) or 1.0
        unit = [w / norm for w in weights]
        probes.append((f"dir-pos:{name}", "head_direction", unit))
        probes.append((f"dir-neg:{name}", "head_direction", [-v for v in unit]))
    for index in (0, 96, 192, 288, dim - 1):
        vector = [0.0] * dim
        vector[index] = 1.0
        probes.append((f"axis:{index}", "basis_axis", vector))
    rng = random.Random(PROBE_SEED)
    for i in range(16):
        vector = [rng.gauss(0.0, 1.0) for _ in range(dim)]
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        probes.append((f"gauss:{i}", "seeded_gaussian", [v / norm for v in vector]))
    for i in range(4):
        vector = [rng.gauss(0.0, 1.0) for _ in range(dim)]
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        probes.append((f"gauss-scaled:{i}", "seeded_gaussian_scaled", [2.0 * v / norm for v in vector]))
    return [
        {
            "probe_id": probe_id,
            "kind": kind,
            "embedding": [round(float(v), 6) for v in vector],
        }
        for probe_id, kind, vector in probes
    ]


def write_golden(artifact: dict[str, Any], golden_path: Path) -> int:
    """Rewrite the golden file's constructed-probe section.

    Rows with ``kind == "synthetic_generator"`` already in the file are
    preserved verbatim: they are produced by
    ``scripts/generate_minilm_golden.py`` (which needs the ML environment)
    and cannot be regenerated by this stdlib-only gate. The constructed
    probes below them are regenerated from the artifact.
    """
    preserved: list[str] = []
    if golden_path.is_file():
        for line in golden_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("kind") == "synthetic_generator":
                preserved.append(line)
    probes = generate_probes(artifact)
    golden_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(
            {
                "probe_id": "__meta__",
                "kind": "seed_cases_v2",
                "note": (
                    "Two provenances, labeled per row. kind=synthetic_generator: "
                    "frozen cases derived from the classifier's training-distribution "
                    "generator (dual_lineage.learning.synthetic, seed = training seed, "
                    "dataset fingerprint asserted at generation time), embedded with "
                    "the pinned MiniLM model, carrying the generator's ground-truth "
                    "labels -- synthetic provenance, NOT live traffic. "
                    "kind in (zero, head_direction, basis_axis, seeded_gaussian, "
                    "seeded_gaussian_scaled): constructed seed probes from the "
                    "classifier's documented head structure, kept for embedding-space "
                    "extremes generated text does not reach. Regenerate the labeled "
                    "cases with scripts/generate_minilm_golden.py and the constructed "
                    "probes with this script's `golden` command, only together with "
                    "a new baseline after an intentional retrain."
                ),
                "artifact_version": artifact["artifact_version"],
                "probe_seed": PROBE_SEED,
            }
        )
    ]
    lines.extend(preserved)
    for probe in probes:
        expected = score_embedding(artifact, probe["embedding"])
        lines.append(json.dumps({**probe, "expected": expected}))
    golden_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(probes)


def load_golden(golden_path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in golden_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if not str(row.get("probe_id", "")).startswith("__"):
                rows.append(row)
    return rows


def load_empirical(empirical_path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in empirical_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if not str(row.get("probe_id", "")).startswith("__"):
                rows.append(row)
    return rows


def _empirical_section(empirical_path: Path) -> dict[str, Any]:
    """Empirical score-distribution section for the baseline.

    Distributions come from the locked empirical scores file produced by
    ``scripts/generate_minilm_golden.py`` (current artifact scored over a
    deterministic sample of the synthetic generator). No ``created_at`` is
    recorded anywhere in the baseline: regeneration must be byte-stable.
    """
    if not empirical_path.is_file():
        return {"present": False}
    rows = load_empirical(empirical_path)
    distributions = {
        head: _distribution([float(r[field]) for r in rows])
        for head, field in SCORE_FIELDS.items()
    }
    return {
        "present": True,
        "path": empirical_path.relative_to(ROOT).as_posix()
        if empirical_path.is_relative_to(ROOT)
        else str(empirical_path),
        "sha256": _sha256_file(empirical_path),
        "rows": len(rows),
        "provenance": (
            "synthetic_generator: current artifact scored over a deterministic "
            "stride sample of dual_lineage.learning.synthetic (seed = training "
            "seed). Replace with captured shadow traffic once a capture log "
            "exists; re-lock with scripts/generate_minilm_golden.py + "
            "`minilm_drift_check.py baseline`."
        ),
        "score_distributions": distributions,
    }


def build_baseline(
    artifact_path: Path,
    golden_path: Path,
    empirical_path: Path = DEFAULT_EMPIRICAL,
) -> dict[str, Any]:
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    errors = validate_artifact(artifact)
    if errors:
        raise ValueError(f"refusing to lock an invalid artifact: {errors}")
    if not golden_path.is_file():
        write_golden(artifact, golden_path)
    probes = load_golden(golden_path)
    distributions = {
        name: _distribution([score_embedding(artifact, p["embedding"])[name] for p in probes])
        for name in BINARY_HEADS
    }
    golden_result, _ = run_golden_eval(artifact, probes)
    metadata = artifact.get("training_metadata") or {}
    return {
        "schema_version": 2,
        "gate": "minilm_drift_baseline",
        "artifact_path": artifact_path.relative_to(ROOT).as_posix()
        if artifact_path.is_relative_to(ROOT)
        else str(artifact_path),
        "artifact_sha256": _sha256_file(artifact_path),
        "artifact_version": artifact["artifact_version"],
        "embedding_model": artifact["embedding_model"],
        "embedding_revision": artifact.get("embedding_revision"),
        "embedding_dim": artifact["embedding_dim"],
        "escalation_threshold": artifact["escalation_threshold"],
        "dataset_fingerprint": metadata.get("dataset_fingerprint"),
        "training_seed": metadata.get("seed"),
        "heads": {name: _head_summary(artifact[name]) for name in BINARY_HEADS},
        "task_classes": {
            name: _head_summary(artifact["task_classes"][name]) for name in TASK_CLASSES
        },
        "golden": {
            "path": golden_path.relative_to(ROOT).as_posix()
            if golden_path.is_relative_to(ROOT)
            else str(golden_path),
            "sha256": _sha256_file(golden_path),
            "probe_count": len(probes),
            "labeled_probe_count": golden_result.get("labeled_probe_count", 0),
            "label_agreement": golden_result.get("label_agreement"),
            "score_distributions": distributions,
        },
        "empirical": _empirical_section(empirical_path),
        "thresholds": {
            "psi_warn": PSI_WARN,
            "psi_fail": PSI_FAIL,
            "kl_warn": KL_WARN,
            "kl_fail": KL_FAIL,
            "golden_score_tolerance": GOLDEN_SCORE_TOLERANCE,
            "label_agreement_tolerance": LABEL_AGREEMENT_TOLERANCE,
        },
    }


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def run_golden_eval(
    artifact: dict[str, Any], probes: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    max_delta = 0.0
    labeled = 0
    agreement_hits: dict[str, int] = {name: 0 for name in BINARY_HEADS}
    agreement_hits["task_class"] = 0
    for probe in probes:
        errors = validate_embedding(probe.get("embedding"), artifact["embedding_dim"])
        if errors:
            failures.append(f"probe {probe.get('probe_id')}: {errors[0]}")
            continue
        actual = score_embedding(artifact, probe["embedding"])
        expected = probe["expected"]
        for name in BINARY_HEADS:
            delta = abs(actual[name] - expected[name])
            max_delta = max(max_delta, delta)
            if delta > GOLDEN_SCORE_TOLERANCE:
                failures.append(
                    f"probe {probe['probe_id']}: {name} score moved {delta:.4f} "
                    f"(expected {expected[name]:.4f}, got {actual[name]:.4f})"
                )
        if actual["task_class"] != expected["task_class"]:
            failures.append(
                f"probe {probe['probe_id']}: task_class flipped "
                f"{expected['task_class']} -> {actual['task_class']}"
            )
        if actual["would_escalate"] != expected["would_escalate"]:
            failures.append(f"probe {probe['probe_id']}: would_escalate flipped")
        labels = probe.get("labels")
        if isinstance(labels, dict):
            labeled += 1
            for name in ("complexity", "risk", "uncertainty"):
                decision = actual[name] >= 0.5
                agreement_hits[name] += decision == bool(labels[name])
            agreement_hits["escalation"] += (
                actual["would_escalate"] == bool(labels["escalation"])
            )
            agreement_hits["task_class"] += actual["task_class"] == labels["task_class"]
    result: dict[str, Any] = {"probe_count": len(probes), "max_score_delta": max_delta}
    if labeled:
        result["labeled_probe_count"] = labeled
        result["label_agreement"] = {
            name: hits / labeled for name, hits in agreement_hits.items()
        }
    return result, failures


def run_check(
    artifact_path: Path,
    baseline_path: Path,
    golden_path: Path,
    observed_path: Path | None = None,
) -> tuple[dict[str, Any], int]:
    evidence: dict[str, Any] = {
        "gate": "minilm_drift",
        "decision": "pass",
        "artifact": str(artifact_path),
        "generated_at": datetime.now(UTC).isoformat(),
        "errors": [],
        "warnings": [],
    }
    errors: list[str] = evidence["errors"]
    warnings: list[str] = evidence["warnings"]
    if not artifact_path.is_file():
        errors.append(f"artifact not found: {artifact_path}")
        evidence["decision"] = "fail"
        return evidence, 1
    if not baseline_path.is_file():
        errors.append(
            f"baseline not found: {baseline_path}; lock one with "
            "`python scripts/minilm_drift_check.py baseline`"
        )
        evidence["decision"] = "fail"
        return evidence, 1
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    validation_errors = validate_artifact(artifact)
    evidence["validation_errors"] = validation_errors
    errors.extend(validation_errors)
    if validation_errors:
        evidence["decision"] = "fail"
        return evidence, 1

    # Control 1: baseline lock.
    actual_sha = _sha256_file(artifact_path)
    evidence["artifact_sha256"] = actual_sha
    evidence["baseline_artifact_sha256"] = baseline.get("artifact_sha256")
    if actual_sha != baseline.get("artifact_sha256"):
        errors.append(
            "artifact SHA-256 differs from the locked baseline; if this retrain is "
            "intentional, regenerate the golden set and baseline "
            "(`make minilm-drift-baseline`) in the same change"
        )
    for field in ("embedding_model", "embedding_revision", "embedding_dim", "escalation_threshold"):
        if artifact.get(field) != baseline.get(field):
            errors.append(f"{field} differs from baseline: {artifact.get(field)!r} != {baseline.get(field)!r}")

    if not golden_path.is_file():
        errors.append(f"golden probe file not found: {golden_path}")
        evidence["decision"] = "fail"
        return evidence, 1
    if _sha256_file(golden_path) != baseline.get("golden", {}).get("sha256"):
        errors.append("golden probe file differs from the baseline-locked golden SHA-256")
    probes = load_golden(golden_path)

    # Control 4: golden eval.
    golden_result, golden_failures = run_golden_eval(artifact, probes)
    evidence["golden"] = golden_result
    errors.extend(golden_failures)
    locked_agreement = baseline.get("golden", {}).get("label_agreement")
    current_agreement = golden_result.get("label_agreement")
    if locked_agreement and current_agreement:
        for name, locked_value in locked_agreement.items():
            current_value = current_agreement.get(name)
            if (
                current_value is not None
                and locked_value - current_value > LABEL_AGREEMENT_TOLERANCE
            ):
                errors.append(
                    f"golden label agreement for {name} dropped "
                    f"{locked_value:.3f} -> {current_value:.3f} "
                    f"(tolerance {LABEL_AGREEMENT_TOLERANCE})"
                )

    # Control 3: distribution drift of probe scores vs baseline histograms.
    psi_report: dict[str, Any] = {}
    worst = "pass"
    for name in BINARY_HEADS:
        values = [score_embedding(artifact, p["embedding"])[name] for p in probes]
        expected_hist = baseline["golden"]["score_distributions"][name]["histogram"]
        psi = population_stability_index(expected_hist, histogram(values))
        kl = kl_divergence(expected_hist, histogram(values))
        level = _drift_level(psi, kl)
        worst = max(worst, level, key=("pass", "warn", "fail").index)
        psi_report[name] = {"psi": psi, "kl": kl, "decision": level}
    evidence["probe_distribution_drift"] = psi_report
    if worst == "fail":
        errors.append("golden-probe score distribution drift at fail level (see PSI/KL)")
    elif worst == "warn":
        warnings.append("golden-probe score distribution drift at warn level (see PSI/KL)")

    # Optional: observed shadow scores vs the empirical baseline (fails at
    # fail-level drift; legacy probe-baseline fallback stays warn-capped).
    if observed_path is not None:
        observed_report, observed_warnings, observed_errors = _observed_drift(
            artifact, baseline, observed_path
        )
        evidence["observed_drift"] = observed_report
        warnings.extend(observed_warnings)
        errors.extend(observed_errors)

    if errors:
        evidence["decision"] = "fail"
    elif warnings:
        evidence["decision"] = "warn"
    return evidence, 1 if evidence["decision"] == "fail" else 0


def _observed_drift(
    artifact: dict[str, Any], baseline: dict[str, Any], observed_path: Path
) -> tuple[dict[str, Any], list[str], list[str]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []
    for lineno, line in enumerate(observed_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            warnings.append(f"observed line {lineno}: invalid JSON, skipped")
            continue
        if str(row.get("probe_id", "")).startswith("__"):
            continue  # meta lines of a scores file, not predictions
        bad = [
            field
            for head, field in SCORE_FIELDS.items()
            if not _is_finite_number(row.get(field)) or not 0.0 <= float(row[field]) <= 1.0
        ]
        if bad:
            warnings.append(f"observed line {lineno}: invalid score fields {bad}, skipped")
            continue
        rows.append(row)
    empirical = baseline.get("empirical") or {}
    use_empirical = bool(empirical.get("present")) and "score_distributions" in empirical
    report: dict[str, Any] = {
        "rows": len(rows),
        "baseline_source": (
            "empirical_synthetic_generator" if use_empirical else "golden_probes_legacy"
        ),
    }
    if not use_empirical:
        report["decision_capped_at"] = "warn"
    if len(rows) < 30:
        warnings.append(
            f"observed drift needs at least 30 valid score rows, got {len(rows)}; "
            "collect more shadow predictions before trusting PSI/KL"
        )
        return report, warnings, errors
    distributions = (
        empirical["score_distributions"]
        if use_empirical
        else baseline["golden"]["score_distributions"]
    )
    for head, field in SCORE_FIELDS.items():
        values = [float(r[field]) for r in rows]
        expected_hist = distributions[head]["histogram"]
        psi = population_stability_index(expected_hist, histogram(values))
        kl = kl_divergence(expected_hist, histogram(values))
        level = _drift_level(psi, kl)
        report[head] = {"psi": psi, "kl": kl, "decision": level}
        if level == "fail" and use_empirical:
            errors.append(
                f"observed {head} scores drift vs empirical baseline at fail level: "
                f"PSI={psi:.3f} KL={kl:.3f} (thresholds PSI>={PSI_FAIL} / KL>={KL_FAIL})"
            )
        elif level != "pass":
            warnings.append(
                f"observed {head} scores drift vs "
                f"{'empirical' if use_empirical else 'probe'} baseline: "
                f"PSI={psi:.3f} KL={kl:.3f}"
                + ("" if use_empirical else " (legacy probe baseline; review trigger only)")
            )
    return report, warnings, errors


def run_compare(
    artifact_path: Path, candidate_path: Path, golden_path: Path
) -> tuple[dict[str, Any], int]:
    """Control 6: shadow-compare a candidate artifact on the golden probes."""
    evidence: dict[str, Any] = {
        "gate": "minilm_drift_compare",
        "decision": "pass",
        "current": str(artifact_path),
        "candidate": str(candidate_path),
        "generated_at": datetime.now(UTC).isoformat(),
        "errors": [],
        "warnings": [],
    }
    current = json.loads(artifact_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    for label, art in (("current", current), ("candidate", candidate)):
        errs = validate_artifact(art)
        if errs:
            evidence["errors"].append(f"{label} artifact invalid: {errs}")
    if evidence["errors"]:
        evidence["decision"] = "fail"
        return evidence, 1
    if candidate["embedding_dim"] != current["embedding_dim"]:
        evidence["errors"].append("candidate embedding_dim differs from current artifact")
        evidence["decision"] = "fail"
        return evidence, 1
    probes = load_golden(golden_path)
    per_head_max = {name: 0.0 for name in BINARY_HEADS}
    per_head_mean = {name: 0.0 for name in BINARY_HEADS}
    escalation_flips = 0
    task_flips = 0
    for probe in probes:
        now = score_embedding(current, probe["embedding"])
        cand = score_embedding(candidate, probe["embedding"])
        for name in BINARY_HEADS:
            delta = abs(cand[name] - now[name])
            per_head_max[name] = max(per_head_max[name], delta)
            per_head_mean[name] += delta / len(probes)
        escalation_flips += now["would_escalate"] != cand["would_escalate"]
        task_flips += now["task_class"] != cand["task_class"]
    evidence["per_head_max_abs_delta"] = per_head_max
    evidence["per_head_mean_abs_delta"] = per_head_mean
    evidence["escalation_flips"] = escalation_flips
    evidence["task_class_flips"] = task_flips
    worst_delta = max(per_head_max.values())
    if escalation_flips or task_flips or worst_delta > COMPARE_FAIL_DELTA:
        evidence["decision"] = "fail"
        evidence["errors"].append(
            "candidate changes golden-probe decisions or moves a head score by "
            f">{COMPARE_FAIL_DELTA}; it needs a new baseline + promotion review, "
            "not a silent swap"
        )
    elif worst_delta > COMPARE_WARN_DELTA:
        evidence["decision"] = "warn"
        evidence["warnings"].append("candidate moves golden-probe scores at warn level")
    return evidence, 1 if evidence["decision"] == "fail" else 0


def run_sample(
    predictions_path: Path, output_path: Path, sample_size: int, threshold: float
) -> tuple[dict[str, Any], int]:
    """Control 8: deterministic human-review sample from shadow predictions."""
    rows: list[dict[str, Any]] = []
    for line in predictions_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    valid = [
        r
        for r in rows
        if _is_finite_number(r.get("escalation_probability"))
        and _is_finite_number(r.get("uncertainty_score"))
    ]

    def near_threshold(row: dict[str, Any]) -> float:
        return abs(float(row["escalation_probability"]) - threshold)

    near = sorted(valid, key=near_threshold)
    half = sample_size // 2
    picked: list[tuple[dict[str, Any], str]] = [
        (r, "near_escalation_threshold") for r in near[:half]
    ]
    chosen = {id(r) for r, _ in picked}
    uncertain = sorted(
        (r for r in valid if id(r) not in chosen),
        key=lambda r: -float(r["uncertainty_score"]),
    )
    quarter = sample_size // 4
    picked += [(r, "high_uncertainty") for r in uncertain[:quarter]]
    chosen = {id(r) for r, _ in picked}
    remainder = [r for r in valid if id(r) not in chosen]
    rng = random.Random(PROBE_SEED)
    rng.shuffle(remainder)
    picked += [(r, "seeded_random") for r in remainder[: sample_size - len(picked)]]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row, reason in picked:
            handle.write(json.dumps({**row, "review_reason": reason}) + "\n")
    evidence = {
        "gate": "minilm_review_sample",
        "decision": "pass",
        "input_rows": len(rows),
        "valid_rows": len(valid),
        "sampled": len(picked),
        "output": str(output_path),
        "threshold": threshold,
    }
    return evidence, 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _emit(evidence: dict[str, Any], output: str | None) -> None:
    text = json.dumps(evidence, indent=2)
    print(text)
    target = output or os.getenv("MINILM_DRIFT_OUTPUT")
    if target:
        Path(target).write_text(text + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    command = "check"
    if args_list and args_list[0] in {"check", "baseline", "golden", "compare", "sample"}:
        command = args_list.pop(0)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--observed", type=Path, default=None, help="JSONL of shadow scores")
    parser.add_argument("--candidate", type=Path, default=None, help="candidate artifact (compare)")
    parser.add_argument("--sample-size", type=int, default=50)
    parser.add_argument("--output", default=None, help="also write evidence JSON here")
    args = parser.parse_args(args_list)

    if command == "golden":
        artifact = json.loads(args.artifact.read_text(encoding="utf-8"))
        errs = validate_artifact(artifact)
        if errs:
            _emit({"gate": "minilm_drift_golden", "decision": "fail", "errors": errs}, args.output)
            return 1
        count = write_golden(artifact, args.golden)
        _emit(
            {"gate": "minilm_drift_golden", "decision": "pass", "probes": count,
             "golden": str(args.golden), "sha256": _sha256_file(args.golden)},
            args.output,
        )
        return 0
    if command == "baseline":
        try:
            baseline = build_baseline(args.artifact, args.golden)
        except ValueError as exc:
            _emit({"gate": "minilm_drift_baseline", "decision": "fail", "errors": [str(exc)]}, args.output)
            return 1
        args.baseline.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
        _emit(
            {"gate": "minilm_drift_baseline", "decision": "pass",
             "baseline": str(args.baseline), "artifact_sha256": baseline["artifact_sha256"]},
            args.output,
        )
        return 0
    if command == "compare":
        if args.candidate is None:
            parser.error("compare requires --candidate")
        evidence, code = run_compare(args.artifact, args.candidate, args.golden)
        _emit(evidence, args.output)
        return code
    if command == "sample":
        if args.observed is None:
            parser.error("sample requires --observed predictions.jsonl")
        output_path = Path(args.output) if args.output else ROOT / "artifacts" / "minilm-review-sample.jsonl"
        artifact = json.loads(args.artifact.read_text(encoding="utf-8"))
        evidence, code = run_sample(
            args.observed, output_path, args.sample_size, float(artifact["escalation_threshold"])
        )
        print(json.dumps(evidence, indent=2))
        return code
    evidence, code = run_check(args.artifact, args.baseline, args.golden, args.observed)
    _emit(evidence, args.output)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
