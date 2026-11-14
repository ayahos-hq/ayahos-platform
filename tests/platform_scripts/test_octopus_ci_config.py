"""Prevent accidental removal of mandatory Octopus verification gates."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LANES = (
    "api-postgres", "web-site", "ml-cpu", "rag-postgres",
    "ruby-worker", "ruby-control", "release-hardening",
)
PARAMETERS = ("api", "web", "ml", "rag", "worker", "control", "release")


def test_octopus_preserves_queued_and_running_exact_sha_verifications() -> None:
    """A push on another branch must not cancel the queued exact-SHA CI task.

    Octopus supersedes queued deployments per project/environment/tenant,
    not per Git ref. Multiple feature branches share our CI environment;
    dropping queued tasks makes release acceptance impossible during activity.
    """
    settings = (ROOT / ".octopus/deployment_settings.ocl").read_text(encoding="utf-8")
    assert re.search(r"(?m)^cancel_running_tasks\s*=\s*false\s*$", settings)
    assert re.search(r"(?m)^cancel_queued_tasks\s*=\s*false\s*$", settings)


def test_octopus_required_steps_cover_all_verification_lanes() -> None:
    source = (ROOT / ".octopus/deployment_process.ocl").read_text(encoding="utf-8")
    names = re.findall(r'^step "([\w-]+)" \{', source, re.MULTILINE)
    arguments = re.findall(
        r'Octopus.Action.Script.ScriptParameters\s*=\s*"([\w-]+)"', source
    )
    # The deployable-container-smoke step is an additional required gate on top
    # of the verification lanes: it runs its own script, takes no lane parameter
    # and uses no execution container, so only the step/required/source/pool
    # counts include it.
    assert names == [*LANES, "deployable-container-smoke", "public-live-chat"]
    assert arguments == [*PARAMETERS, "live-chat"]
    assert source.count("is_required = true") == len(LANES) + 2
    assert source.count('Octopus.Action.Script.ScriptSource = "GitRepository"') == len(LANES) + 2
    assert source.count('worker_pool = "hosted-ubuntu"') == len(LANES) + 2
    assert source.count("        container {\n            feed = \"docker-hub-public\"\n            image = \"octopusdeploy/worker-tools:6.6.5-ubuntu.24.04\"") == len(LANES) + 1
    assert 'environments = ["production"]' in source
    assert 'ScriptFileName = "scripts/ci/octopus_verify.sh"' in source
    assert 'ScriptFileName = "scripts/ci/deployable-container-smoke.sh"' in source
    assert "octopusdeploy/worker-tools:ubuntu.24.04" not in source


def test_octopus_source_and_bash_guards_are_present() -> None:
    script = (ROOT / "scripts/ci/octopus_verify.sh").read_text(encoding="utf-8")
    verify = (ROOT / "scripts/ci/verify.sh").read_text(encoding="utf-8")
    assert 'set -euo pipefail' in script
    assert 'pg_ctlcluster 16 main start' in script
    assert 'CREATE EXTENSION IF NOT EXISTS vector' in script
    assert 'python scripts/release_gate.py' in script
    assert 'RAG_REQUIRE_PGVECTOR=1' in script
    assert 'RUBY_WORKER_REQUIRE_INTEGRATION=1' in script
    assert '127.0.0.1:5432/ayahos_ci' in script
    assert 'python3.12 -m venv "$ROOT/.venv"' in script
    assert 'if [ "${APT_UPDATED:-0}" -eq 0 ]; then' in script
    assert 'install_packages ruby ruby-dev build-essential libpq-dev' in script
    assert 'install_packages ruby-full' not in script
    assert 'ruby_gem_bin="$(ruby -e \'print Gem.bindir\')"' in script
    assert 'if ! command -v bundle >/dev/null 2>&1; then' in script
    assert 'command -v bundle >/dev/null 2>&1 || fail "Ruby Bundler unavailable"' in script
    assert '    rag)\n        CI_STAGE="ruby-bootstrap"' in script
    assert 'setup_python' not in script.split('    rag)\n', 1)[1].split('\n        ;;', 1)[0]
    assert '    rag)\n        setup_python' not in script
    assert 'Octopus.Release.Git.CommitHash' in script
    assert 'export LIVE_EXPECTED_SHA' in script
    assert '^[0-9a-fA-F]{7,64}$' not in script
    assert 'command -v bundle >/dev/null 2>&1 ||' in script
    assert 'fail "Ruby Bundler unavailable"' in script
    assert 'production' not in script.lower()
    assert 'apps/sandbox_worker/tests --ignore=apps/sandbox_worker/tests/test_e2e_gvisor.py' in verify
    assert 'wait_for_pg_isready' in verify
    assert verify.index('wait_for_pg_isready') < verify.index('bundle install --jobs 1 --retry 2')
    assert 'bundle install --jobs 1 --retry 2' in verify
    assert 'trap \'ci_log_failure "$?" "$LANE" "$CI_STAGE"\' ERR' in script
    assert 'ci_run_stage' not in script
    assert 'CI_STAGE="pgvector-tests"' in script
    assert 'bash scripts/ci/verify.sh rag' in script
    assert 'pg_conftool 16 main set shared_buffers 32MB' in script
    assert 'pg_conftool 16 main set max_parallel_workers 0' in script
    assert 'ci_resource_snapshot "postgres:before-start:$LANE"' in script


def test_default_sandbox_gate_excludes_image_backed_e2e() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert 'apps/sandbox_worker/tests --ignore=apps/sandbox_worker/tests/test_e2e_gvisor.py' in makefile


def test_numpy_dependency_stays_compatible_with_python_311_mypy_target() -> None:
    """Keep the lowest supported Python target on a NumPy-stub-compatible release."""
    source = (ROOT / "apps/api/pyproject.toml").read_text(encoding="utf-8")
    assert 'python_version = "3.11"' in source
    assert 'numpy>=1.26.0,<2.5.0' in source


def test_octopus_resource_diagnostics_do_not_mask_sigkill() -> None:
    command = (
        "set -euo pipefail; "
        "source scripts/ci/resource_diagnostics.sh; "
        "trap 'ci_log_failure \"$?\" rag simulated' ERR; "
        "bash -c 'exit 137'"
    )
    result = subprocess.run(
        ["bash", "-c", command], cwd=ROOT, text=True,
        capture_output=True, check=False,
    )
    assert result.returncode == 137
    assert "CI_RESOURCE stage=worker:error:rag:simulated:exit=137" in result.stdout
    assert "SIGKILL alone does not prove OOM" in result.stderr


def test_octopus_rag_bootstrap_stops_on_setup_failure() -> None:
    script = (ROOT / "scripts/ci/octopus_verify.sh").read_text(encoding="utf-8")
    rag_block = script.split("    rag)\n", 1)[1].split("\n        ;;", 1)[0]
    command = (
        "set -euo pipefail\n"
        "source scripts/ci/resource_diagnostics.sh\n"
        "LANE=rag; CI_STAGE=startup\n"
        "trap 'ci_log_failure \"$?\" \"$LANE\" \"$CI_STAGE\"' ERR\n"
        "setup_ruby() { return 42; }\n"
        "setup_pgvector() { echo POSTGRES_SHOULD_NOT_RUN; }\n"
        + rag_block + "\n"
    )
    result = subprocess.run(
        ["bash", "-c", command], cwd=ROOT, text=True,
        capture_output=True, check=False,
    )
    assert result.returncode == 42
    assert "CI_RESOURCE stage=rag:before-ruby-bootstrap" in result.stdout
    assert "CI_RESOURCE stage=worker:error:rag:ruby-bootstrap:exit=42" in result.stdout
    assert "POSTGRES_SHOULD_NOT_RUN" not in result.stdout


def test_postgres_readiness_exits_on_killed_probe() -> None:
    verify = (ROOT / "scripts/ci/verify.sh").read_text(encoding="utf-8")
    function = verify.split("wait_for_pg_isready() {", 1)[1].split("\nwait_for_db() {", 1)[0]
    command = (
        'source scripts/ci/resource_diagnostics.sh; '
        'pg_isready() { return 137; }; '
        'TEST_DATABASE_URL=postgresql://localhost/ci; '
        'wait_for_pg_isready() {' + function + "\nwait_for_pg_isready"
    )
    result = subprocess.run(
        ["bash", "-c", command], cwd=ROOT, text=True,
        capture_output=True, check=False,
    )
    assert result.returncode == 137
    assert "not a normal not-ready result" in result.stderr
    assert "CI_RESOURCE stage=pg_isready:signal:137" in result.stdout


def test_octopus_shell_scripts_parse() -> None:
    for path in (
        "scripts/ci/resource_diagnostics.sh",
        "scripts/ci/verify.sh",
        "scripts/ci/octopus_verify.sh",
    ):
        result = subprocess.run(
            ["bash", "-n", path], cwd=ROOT, text=True,
            capture_output=True, check=False,
        )
        assert result.returncode == 0, f"{path}: {result.stderr}"


def test_octopus_live_lane_runs_post_deploy_checks() -> None:
    script = (ROOT / "scripts/ci/octopus_verify.sh").read_text(encoding="utf-8")
    assert "release|live" in script
    assert "scripts/ci/post-deploy.sh" in script
    post_deploy = (ROOT / "scripts/ci/post-deploy.sh").read_text(encoding="utf-8")
    assert "scripts/live_e2e.sh" in post_deploy
    assert "scripts/ci/live-release.sh" in post_deploy
    canary = (ROOT / "scripts/ci/canary.sh").read_text(encoding="utf-8")
    assert "public_chat_smoke.rb" in canary


def test_consistency_checks_are_wired_into_the_gates() -> None:
    verify = (ROOT / "scripts/ci/verify.sh").read_text(encoding="utf-8")
    assert "check_service_inventory.rb" in verify
    assert "verify_weight_inventory.py" in verify
    assert "scripts/migration" in verify
    assert "run_consistency_checks" in verify
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "consistency-check" in makefile
