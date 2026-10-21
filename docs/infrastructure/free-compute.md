# Free compute for AyahOS Dual-Lineage

## Recommended: GitHub Codespaces

Use Codespaces for dependency installation, lint/type checks, CPU MiniLM training, and short-lived development work.

Personal GitHub accounts include a monthly free Codespaces quota. Keep the codespace stopped when idle and delete old codespaces to avoid consuming storage quota.

### Start

1. Push `AyahOS_Dual_lineage` to a personal GitHub repository.
2. Open the repository on GitHub.
3. Select **Code -> Codespaces -> Create codespace on main**.
4. Wait for `scripts/bootstrap_codespace.sh` to finish. It installs dependencies and caches the pinned MiniLM revision with a checksum/license manifest.
5. Run:

```bash
make check
make minilm-seed
make minilm-train MINILM_VERSION=minilm-shadow-v1
```

The heavyweight model cache stays under `models/cache/` and is ignored by Git. Reproducibility metadata is written to `models/manifests/all-MiniLM-L6-v2.json`.

The devcontainer intentionally uses GitHub's default Linux base instead of a custom Docker image. This keeps setup smaller and lets GitHub supply the standard base environment.

## Persistent alternative: Oracle Cloud Always Free

OCI Always Free is better when Ayah needs a VM that remains online between sessions. Use Ubuntu on an Always Free Ampere A1 shape and keep the instance inside the account's Always Free limits.

ARM64 is suitable for the Python control plane and CPU inference/training, but validate every native dependency before treating the instance as a deployment target.

## Not recommended for this workload

Google Cloud's permanent free Compute Engine allowance is an e2-micro VM. It is useful for tiny services but too constrained for the PyTorch/Sentence Transformers development environment used here.

## Cost safety

- Do not enable paid overage just to complete model training.
- Stop Codespaces when idle.
- Keep cloud-model training artifacts reproducible so a disposable machine can be deleted without losing source-of-truth data.
- Node-001 remains the preferred local GPU execution target once the artifact is trained.
