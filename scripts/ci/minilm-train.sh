#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
export TOKENIZERS_PARALLELISM=false
export MINILM_MODEL_ID=sentence-transformers/all-MiniLM-L6-v2
export MINILM_REVISION=1110a243fdf4706b3f48f1d95db1a4f5529b4d41
export HF_HOME="$PWD/.cache/huggingface"
python -m pip install 'torch>=2.5,<3' --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r ml-requirements.txt
python scripts/cache_minilm.py \
  --repo-id "$MINILM_MODEL_ID" --revision "$MINILM_REVISION" \
  --output-dir models/cache/sentence-transformers/all-MiniLM-L6-v2 \
  --manifest models/manifests/all-MiniLM-L6-v2.json
PYTHONPATH=apps/api/src python -m dual_lineage.learning.synthetic \
  --output benchmarks/datasets/generated/minilm_seed_v1.jsonl --count 12000 --seed 20260927
test "$(wc -l < benchmarks/datasets/generated/minilm_seed_v1.jsonl)" -eq 12000
PYTHONPATH=apps/api/src python -m dual_lineage.learning.training_cli \
  --dataset benchmarks/datasets/generated/minilm_seed_v1.jsonl \
  --artifact models/classifiers/minilm-shadow-v1.json \
  --report experiments/minilm-shadow-v1-report.json \
  --version minilm-shadow-v1 --seed 20260927 \
  --model-id "$MINILM_MODEL_ID" --revision "$MINILM_REVISION" \
  --local-path models/cache/sentence-transformers/all-MiniLM-L6-v2 \
  --evidence-source synthetic
PYTHONPATH=apps/api/src python - <<'PY'
import json
import os
from pathlib import Path
from dual_lineage.learning.promotion import evaluate_promotion
from dual_lineage.learning.training import MiniLMTrainingReport

report = MiniLMTrainingReport.model_validate_json(
    Path("experiments/minilm-shadow-v1-report.json").read_text()
)
decision = evaluate_promotion(report)
assert report.evidence_source == "synthetic"
assert not decision.eligible_for_advisory
assert "operational_evidence_required" in decision.reasons
Path("experiments/minilm-shadow-v1-promotion.json").write_text(
    decision.model_dump_json(indent=2) + "\n"
)
rev = os.environ["MINILM_REVISION"]
artifact = json.loads(Path("models/classifiers/minilm-shadow-v1.json").read_text())
manifest = json.loads(Path("models/manifests/all-MiniLM-L6-v2.json").read_text())
assert artifact["embedding_revision"] == rev
assert artifact["training_metadata"]["embedding_revision"] == rev
assert report.embedding_revision == rev
assert manifest["requested_revision"] == rev
assert manifest["resolved_revision"] == rev
assert manifest["embedding_dim"] == 384
assert manifest["file_count"] > 0
print("Synthetic evidence holds authority promotion; provenance verified")
PY
sha256sum models/classifiers/minilm-shadow-v1.json \
  models/manifests/all-MiniLM-L6-v2.json \
  experiments/minilm-shadow-v1-report.json \
  experiments/minilm-shadow-v1-promotion.json \
  > experiments/minilm-shadow-v1-sha256.txt
