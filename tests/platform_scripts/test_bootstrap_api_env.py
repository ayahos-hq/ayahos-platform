"""Contract tests for the cross-platform API dependency bootstrap."""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/ci/bootstrap_api_env.py"
spec = importlib.util.spec_from_file_location("bootstrap_api_env", SCRIPT)
assert spec and spec.loader
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


def test_bootstrap_installs_single_canonical_api_extra_set(tmp_path):
    cmds = bootstrap.commands(tmp_path / ".venv")
    assert len(cmds) == 3
    assert cmds[1][-1].endswith("apps/api[dev,control]") or cmds[1][-1].endswith("apps\\api[dev,control]")
    assert cmds[2][-2:] == ["pip", "check"]


def test_bootstrap_uses_platform_appropriate_python(tmp_path):
    cmds = bootstrap.commands(tmp_path / ".venv")
    expected = "Scripts/python.exe" if bootstrap.os.name == "nt" else "bin/python"
    assert Path(cmds[1][0]).parts[-2:] == Path(expected).parts[-2:]


def test_bootstrap_can_skip_check_for_offline_setup(tmp_path):
    assert len(bootstrap.commands(tmp_path / ".venv", verify=False)) == 2



def test_make_install_api_uses_shared_bootstrap():
    makefile = (SCRIPT.parents[2] / 'Makefile').read_text(encoding='utf-8')
    block = makefile.split('install-api:', 1)[1].split('install-ml:', 1)[0]
    assert 'scripts/ci/bootstrap_api_env.py' in block
    assert 'pip install' not in block


def test_ci_checks_dependency_integrity_after_install():
    root = SCRIPT.parents[2]
    verify = (root / "scripts/ci/verify.sh").read_text(encoding="utf-8")
    octopus = (root / "scripts/ci/octopus_verify.sh").read_text(encoding="utf-8")
    assert "python -m pip install -e './apps/api[dev,control]'\n    python -m pip check" in verify
    assert ".venv/bin/python -m pip install -e './apps/api[dev,control]'\n    .venv/bin/python -m pip check" in verify
    assert "python -m pip install -e './apps/api[dev,control]'\n        python -m pip check" in octopus
