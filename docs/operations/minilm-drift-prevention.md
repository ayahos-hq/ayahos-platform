# MiniLM shadow classifier — drift prevention

The MiniLM shadow head (`models/classifiers/minilm-shadow-v1.json`) is
shadow-only: it records signals and never mutates a `ControlEnvelope`
(AGENTS.md invariant 2). Drift controls for it therefore protect the
*evidence* it produces — a silently changed artifact would poison
calibration and promotion decisions long before anyone noticed.

All controls live in one stdlib-only, offline gate:
`scripts/minilm_drift_check.py` (tests:
`apps/api/tests/test_minilm_drift_check.py`). It runs in the
consistency lane (`make consistency-check`, `scripts/ci/verify.sh`)
and standalone via `make minilm-drift-check`.

## The eight controls

1. **Baseline lock.** `benchmarks/datasets/golden/minilm-shadow-v1.baseline.json`
   records the artifact SHA-256, embedding model + pinned revision,
   dimension, escalation threshold, training dataset fingerprint/seed,
   per-head weight statistics and weight hashes, and the golden-probe
   score distributions. `check` fails if the live artifact differs.
   A baseline is only re-locked together with an intentional retrain:
   `make minilm-drift-baseline` (regenerates golden probes, then the
   baseline) in the same change as the new artifact. The baseline lives
   next to the golden probes, not under `models/`, because
   `scripts/verify_weight_inventory.py` treats every `models/**/*.json`
   as a weight artifact that must appear in the weight inventory.
2. **Input validation.** The gate validates the artifact before scoring:
   every head must have exactly `embedding_dim` finite weights, finite
   bias/calibration values, a supported calibration method, a threshold
   in (0, 1), a 40-hex embedding revision, and exactly the four task
   classes. Probe embeddings and observed score rows are validated the
   same way; malformed observed rows are skipped with a warning, never
   scored. At runtime, `MiniLMArtifact` (pydantic) and
   `MiniLMShadowClassifier.predict_with_embedding` already enforce the
   same shape on load and per prediction.
3. **Distribution monitoring.** `check` recomputes the golden-probe
   score distribution for each head and reports PSI and KL divergence
   against the baseline histograms: pass < 0.10, warn < 0.25,
   fail >= 0.25. With recorded shadow predictions,
   `check --observed predictions.jsonl` compares live score
   distributions against the baseline's **empirical distribution**:
   the current artifact scored over a 1,200-case deterministic stride
   sample of the synthetic training-distribution generator (locked in
   the baseline's `empirical` section from
   `benchmarks/datasets/golden/minilm-shadow-empirical-v1.jsonl`,
   produced by `scripts/generate_minilm_golden.py`). That comparison
   now **fails** at the same PSI/KL fail thresholds — it is no longer
   warn-capped. Provenance honesty: the empirical baseline is
   synthetic-generator-derived, because no captured shadow-traffic
   score log exists in the repo yet. When one does, re-lock the
   empirical section from real captured scores the same way and this
   caveat disappears; until then a fail means "distribution moved
   decisively away from the training distribution," which is the drift
   this gate exists to catch. (A baseline file that predates the
   empirical section still falls back to the old probe comparison,
   capped at `warn`.)
4. **Golden eval.** `benchmarks/datasets/golden/minilm-shadow-golden-v1.jsonl`
   is a frozen set of 186 cases with the scores the locked artifact
   produced. 144 of them are **derived from the classifier's own
   training-distribution generator** (`dual_lineage.learning.synthetic`,
   one case per scenario family): at generation time the script asserts
   the regenerated dataset fingerprint equals the artifact's
   `training_metadata.dataset_fingerprint`, embeds each prompt with the
   pinned MiniLM model (the repo's `OnnxMiniLMEmbedder`), and freezes
   the generator's ground-truth labels next to the expected scores.
   `check` therefore verifies both score stability *and* agreement with
   the generator labels — it fails if any score moves more than 0.02,
   any task-class / escalation decision flips, or label agreement for
   any head drops more than 0.05 below the locked agreement (currently
   1.0 on all heads for these family representatives). The remaining 42
   cases are the original *constructed seed probes* (zero vector, ± each
   head's unit weight direction, basis axes, seeded Gaussian vectors),
   kept because they cover embedding-space extremes that generated text
   never reaches; they carry no labels. Provenance is labeled per row
   (`kind`) and in the file's `__meta__` line. Honest limit: the labeled
   cases come from the *training distribution's own generator* — the
   classifier has no real-traffic labeled dataset yet, so this eval
   detects artifact/distribution drift, not real-world accuracy loss
   (AGENTS.md invariant 8: synthetic performance is not operational
   evidence).
5. **No retraining on own outputs.** Shadow predictions are telemetry,
   never training labels. Retraining uses only the synthetic seed
   generator (`make minilm-seed`) or consented operational exports
   (`make operational-export`) — the same boundary
   `training_metadata.evidence_source` and the promotion gate already
   encode: synthetic evidence cannot promote a classifier by itself,
   and a model trained on its own predictions is a feedback loop, not
   evidence. New artifacts go through the promotion gate
   (`dual_lineage.learning.promotion`) before any status change.
6. **Shadow/canary comparison.** Before swapping an artifact, compare
   it against the current one on the golden probes:
   `python scripts/minilm_drift_check.py compare --candidate new.json`.
   The gate fails on any golden decision flip or a head score moving
   more than 0.10, and warns above 0.02. Passing `compare` never
   promotes anything; it only sizes the change. The candidate still
   runs shadow-only until the promotion gate says otherwise.
7. **Wiring.** `make minilm-drift-check` runs the gate standalone. The
   same command is part of `consistency-check` in the Makefile and of
   `run_consistency_checks` in `scripts/ci/verify.sh`, so CI (Octopus
   consistency lane) fails on artifact/baseline/golden mismatch the
   same way it fails on weight-inventory mismatch.
8. **Human review sampling.** Automated metrics miss semantic drift.
   Weekly (or after any warn), sample recorded shadow predictions for
   eyeball review:
   `python scripts/minilm_drift_check.py sample --observed predictions.jsonl --sample-size 50 --output artifacts/minilm-review-sample.jsonl`.
   The sampler is deterministic: half near-threshold escalations
   (hardest decisions), a quarter highest-uncertainty, the rest a
   seeded random draw. Each row is tagged with its `review_reason`.

## Updating after an intentional retrain

```bash
make minilm-train            # or operational-train; produces a new artifact
python scripts/minilm_drift_check.py compare --candidate models/classifiers/minilm-shadow-v1.json
make minilm-drift-golden     # re-derives labeled golden cases + empirical scores
                             # from the synthetic generator (needs the ML env and
                             # the pinned model snapshot; see the target), then
                             # re-locks the baseline
make minilm-drift-check      # must pass on the new locked state
```

`make minilm-drift-baseline` alone still works for a baseline-only
re-lock: the gate's `golden` command regenerates the constructed probes
and preserves the generator-derived rows verbatim.

Commit the artifact, baseline, golden, and empirical files together.
All four are deterministic (fixed seeds, no timestamps): regenerating
without an artifact change produces byte-identical files, which the
test suite asserts for the baseline. If `minilm-drift-check` fails and
you did not retrain, the artifact on disk is not the artifact that was
locked — treat that as an incident, not a baseline update.

## Capability status

- Controls 1–4, 6–8: **implemented** in `scripts/minilm_drift_check.py`
  (data generation: `scripts/generate_minilm_golden.py`), covered by
  `apps/api/tests/test_minilm_drift_check.py`, and **verified-local**
  against the current `minilm-shadow-v1` artifact (check passes; a
  perturbed copy in /tmp fails on SHA, golden, and PSI; observed drift
  against the empirical baseline fails at fail-level PSI).
  End-to-end verification (2026-10-21, this branch): `make
  consistency-check` and `scripts/ci/verify.sh consistency` both exit
  0; the `verify.sh api` lane was executed step-by-step against a local
  PostgreSQL 16.4 (pip install, schema reset, 21 migrations, mypy clean
  on 138 files, API suite 1179 passed / 1 failed, sandbox-worker suite
  57 passed, release gate passed). The single API-suite failure,
  `test_ruby_client_contract`, reproduces identically on pristine
  `main` (a443a6c) — the committed Ruby client was not regenerated
  after a Python contract change; it is a pre-existing main finding,
  not an effect of this gate. The lane's ruff step also fails on
  pristine main with 4 pre-existing errors in Jev files
  (`jev/client.py`, `test_jev_*`); both findings are recorded here
  rather than fixed in this change, which is scoped to the drift gate.
- Control 5: documented rule above; the training/promotion code paths
  it references already exist (`evidence_source`, promotion gate).
- Observed-traffic PSI (control 3, `--observed`): implemented against
  a locked empirical baseline and fail-capable. The empirical baseline
  is synthetic-generator-derived (no captured shadow-traffic log
  exists yet), so it is **verified-local**, **not verified-live**
  against real traffic.
