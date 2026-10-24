# Linux-native AyahOS developer toolchain

**Scope:** isolated verification and development, not production cutover. The monorepo remains the documented production source of truth until HQ acceptance gates pass. This setup changes only a non-root user's Linux home directory. Do not modify production workers, Render, Cloudflare, Vercel, or secrets.

## Version contract

AyahOS platform's Octopus/bridge checks use Node 22. The Agent Registry gateway also declares Node >=22. A **specific patch version** is pinned for reproducibility while these service contracts are validated. Node 22 remains supported Maintenance LTS; Node 24 adoption requires a separate compatibility upgrade.

- **OS:** Ubuntu 24.04 LTS, Linux x86_64.
- **Node:** v22.23.4; official Linux x64 archive; pinned SHA-256 `1805bcd35e6815559bd2eb97db438d3fdb0eb3a5e6a977b7c1badca76337e9ce`.
- **npm:** bundled 10.9.9.
- **Corepack:** bundled 0.36.0 in the locally verified installation. The canonical monorepo at `dbf9fbde52a11bbc069e19bdeca2658d8dcc1147` pins **pnpm 12.14.0** through `packageManager`, and Corepack selected exactly that version. Other repositories retain their own pins; the Node installer does not replace global pnpm.
- **Python:** per-service `pyproject.toml`. Ubuntu's Python 3.12.3 satisfies the API's `>=3.11` requirement; use per-service virtual environments, not system modifications.
- **Ruby:** Ubuntu Ruby 3.2.3 and Bundler 2.6.9; honor each component's Gemfile.lock and avoid global gem changes.
- **PostgreSQL/pgvector:** only in the dedicated disposable integration lane, not this low-cost developer bootstrap.

Official references: [Node release archive](https://nodejs.org/en/download/archive/v22), [Node release policy](https://github.com/nodejs/Release), and the [AyahOS Linux release gates](https://github.com/fuaadabdullah/AyahOS_Dual_Lineage/blob/docs/linux-first-p0-release-baseline-20261024/docs/infrastructure/linux-release-gates.md).

## Reproducible developer setup

Use a non-root Ubuntu account and checkout on a **native Linux filesystem** such as `/home/USER/src/ayahos/ayahos-platform`. Do not put dependencies and build artifacts under `/mnt/c`.

```bash
bash -n scripts/bootstrap-linux-node.sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s scripts -p test_bootstrap_linux_node.py -v

# Read-only and network-free until explicitly installing:
bash scripts/bootstrap-linux-node.sh --check

# User scoped, official checksum-verified binary:
bash scripts/bootstrap-linux-node.sh --install
export PATH="$HOME/.local/bin:$PATH"
bash scripts/bootstrap-linux-node.sh --check
node --version
npm --version
corepack --version

# When developing a checked-out component with packageManager and nested pnpm scripts:
corepack enable --install-directory "$HOME/.local/bin" pnpm
# In the canonical monorepo checkout, pnpm reports 12.14.0:
# pnpm --version && pnpm install --frozen-lockfile

# Offline regression and provenance, no cloud secrets:
python3 scripts/verify-platform.py
python3 scripts/verify-release-manifest.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run-hq-offline-tests.py
node --test deploy/octopus-github-bridge/test/worker.test.js
```

The installer is idempotent for the pinned version and refuses to overwrite an existing user-local executable/symlink. It verifies the upstream archive against a hardcoded SHA-256 **before extraction**, rejects incomplete installation directories, and never uses `sudo`, `curl | sh`, edits to shell profiles, or unverified mirrors.

For a local-only rollback, first stop all local processes using the binary, verify each of the four symlinks still points at the pinned install, remove just those exact symlinks and that one pinned directory. Do not touch unrelated binaries, other toolchains or production systems.

## Initial verification evidence (2026-10-24 UTC)

- **Environment:** non-root user `pgrun`, Ubuntu 24.04.4 LTS on WSL2, native ext4 checkout under `/home/pgrun/src/ayahos/ayahos-platform`.
- **Install:** pinned Node v22.23.4 installed in `~/.local/opt`, SHA-256 verified before extraction. `--check`, `node -v`, `npm -v` and `corepack -v` passed.
- **Negative controls:** six isolation tests passed for absent installation, mismatched Node version, tampered symlink and refusal to overwrite user binaries.
- **Platform:** 39 script tests and seven Octopus runner tests passed; manifest and source-provenance checks passed.
- **Bridge:** 26 Node bridge tests passed under Linux-native Node.
- **Monorepo frontend on native ext4:** private `main` checkout at `dbf9fbde52a11bbc069e19bdeca2658d8dcc1147`; `pnpm install --frozen-lockfile` passed supply-chain policy checks, all shared/web/site TypeScript checks passed, **295 frontend tests** passed (14 shared + 188 site + 93 web), and both Next.js production builds passed. No deployment occurred.
- **Python/API:** Python 3.12.3 per-repo venv with API development/control extras installed; **1,403 API tests passed, 34 skipped**, and focused 40-test policy/SSE/routing suite, Ruff and mypy all passed. Skipped tests remain outside this gate.
- **Sandbox worker:** **57 tests passed, nine skipped**. Real gVisor isolation is not attested.
- **Ruby:** Ruby 3.2.3 and Bundler 2.6.9, with gems isolated to the non-root user's bundle directory. Workflow worker **128 runs, 646 assertions, 13 skips**; control **20 runs, 79 assertions, zero skips**; RAG **31 runs, 75 assertions, 10 skips**. Database/pgvector skip reasons block real RAG acceptance.
- **Not verified:** complete monorepo `make check` including heavy ML, real PostgreSQL/pgvector contract, authenticated live chat/SSE, independent HQ Octopus, or production rollback.

This is **verified local**, not production acceptance. Record exact commit SHA, OS, exit status and evidence for every subsequent phase.
