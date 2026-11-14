# API development dependency synchronization

Run from any directory:

```sh
python scripts/ci/bootstrap_api_env.py
```

This creates or refreshes the repository's ignored `.venv`, installs the API from its **single authoritative** `apps/api/pyproject.toml` with `[dev,control]` extras, and checks installed dependency consistency. Re-run after pulling changes to the API dependency declarations. On Windows, use `.venv\\Scripts\\python.exe`; on Linux/macOS use `.venv/bin/python`.

Run targeted tests with `.venv/bin/python -m pytest -q apps/api/tests/test_octopus_ci_config.py` (use the Windows interpreter path on Windows). The full Octopus CI pipeline remains responsible for Linux-only Bash, database, Ruby, and container integration gates. This script deliberately does not install heavy ML, Ruby, or deployment tooling and does not modify production or Cloud Run.
