#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -x .venv/bin/python ]]; then
  printf 'Python: '
  .venv/bin/python --version
else
  printf 'Python venv: missing; run make install\n'
fi

if command -v pnpm >/dev/null 2>&1; then
  printf 'pnpm: '
  pnpm --version
else
  printf 'pnpm: missing; run make install\n'
fi

printf 'Branch: '
git branch --show-current
