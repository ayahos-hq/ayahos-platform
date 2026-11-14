#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 --version
node --version
npm --version

make install
make ml-verify
make minilm-cache

printf '\nAyahOS Dual-Lineage Codespace ready.\n'
printf 'Run: make check\n'
printf 'Train: make minilm-seed && make minilm-train\n'
printf 'Pinned MiniLM cache + manifest are already prepared.\n'
