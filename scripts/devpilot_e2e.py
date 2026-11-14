"""Local end-to-end proof of the supervised developer autopilot on real PostgreSQL (Phase 7).

    TEST_DATABASE_URL=postgresql://... .venv/bin/python scripts/devpilot_e2e.py

A harmless planted-bug fixture repository is created in a temporary directory; nothing in this
checkout is modified (that is checked). The run drives the real policy, Action Gateway, tools,
PostgreSQL Spine, and PostgreSQL task store through:

    detect -> task -> evidence -> diagnosis -> approval -> failed patch -> restart and resume
    -> passing patch -> review_requested -> review package -> forbidden-action audit

and writes a redacted evidence artifact to artifacts/devpilot/. The approval step is performed by
this harness standing in for a human operator; the artifact says so. Python, not Ruby, because it
drives Python authority code in-process.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from dual_lineage.actions import (
    ActionCall,
    ActionGateway,
    ActionRegistry,
    ActionRunStatus,
)
from dual_lineage.actions.devpatch import register_patch_tools
from dual_lineage.actions.devtools import (
    NetworkSandbox,
    register_dev_tools,
)
from dual_lineage.actions.safe import FileInspectExecutor
from dual_lineage.brains.contracts import (
    ActionIntent,
    ActionKind,
    PreflightRequest,
)
from dual_lineage.brains.undermind import DeterministicUndermind
from dual_lineage.db import apply_migrations
from dual_lineage.devpilot import (
    FORBIDDEN_TOOLS,
    Actor,
    Approval,
    ApprovalKind,
    RiskClass,
    TaskState,
    autopilot_policy,
    enabled_tools,
)
from dual_lineage.devpilot.ingest import CIFailureReport, CIIngestor
from dual_lineage.devpilot.patching import PatchRequest, prepare_patch
from dual_lineage.devpilot.review import (
    auto_merge_eligibility,
    build_review_package,
    merge_allowed,
    render_markdown,
)
from dual_lineage.devpilot.tasks import (
    DevTaskService,
    EvidenceKind,
    reject_secrets,
)
from dual_lineage.devpilot.workflow import IssueInput, run_diagnosis
from dual_lineage.spine import EventKind, PostgresSpineStore, SharedSpine
from dual_lineage.spine.dev_tasks import PostgresDevTaskStore

CALC_PATH = "apps/api/src/dual_lineage/calc.py"
TEST_PATH = "apps/api/tests/test_calc.py"
FAILING = f"{TEST_PATH}::test_add"
FIXTURE_CALC = "def add(a, b):\n    return a + str(b)  # planted bug\n\n\ndef mul(a, b):\n    return a * b\n"
FIXTURE_TEST = (
    "from dual_lineage.calc import add, mul\n\n\n"
    "def test_add():\n    assert add(2, 3) == 5\n\n\n"
    "def test_mul():\n    assert mul(2, 3) == 6\n"
)
WRONG_FIX = {"path": CALC_PATH, "kind": "replace", "old": "return a + str(b)  # planted bug",
             "new": "return a - b", "reason": "first attempt (deliberately wrong, to exercise rework)"}
RIGHT_FIX = {"path": CALC_PATH, "kind": "replace", "old": "return a - b",
             "new": "return a + b", "reason": "add() must sum numbers"}
TEST_EDIT = {"path": TEST_PATH, "kind": "replace", "old": "def test_mul():",
             "new": "def test_add_negative():\n    assert add(-2, 3) == 1\n\n\ndef test_mul():",
             "reason": "regression test for add()"}
TEST_EDIT_2 = {"path": TEST_PATH, "kind": "replace", "old": "def test_add_negative():",
               "new": "def test_add_negative():  # rework", "reason": "rework keeps the regression test"}


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


def _git_status_if_checkout(root: Path) -> str | None:
    """Return porcelain status, or None when CI supplied a source archive without .git."""
    if not (root / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else None


# Generated and cache directories that tests and installs write to; never part of the source.
_SNAPSHOT_SKIP_DIRS = frozenset({
    ".git", ".venv", "node_modules", "vendor", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".turbo", ".next", "dist", "build", "artifacts",
})


def _source_tree_digest(root: Path) -> str:
    """Hash every source file under root, for archives where git status is unavailable."""
    digest = hashlib.sha256()
    for directory, subdirs, files in os.walk(root):
        subdirs[:] = sorted(name for name in subdirs if name not in _SNAPSHOT_SKIP_DIRS)
        for name in sorted(files):
            path = Path(directory) / name
            if path.is_symlink() or not path.is_file():
                continue
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _checkout_snapshot(root: Path) -> tuple[str, str]:
    """Return ("git", porcelain status) for a checkout, else ("tree-sha256", digest)."""
    status = _git_status_if_checkout(root)
    if status is not None:
        return "git", status
    return "tree-sha256", _source_tree_digest(root)


def _source_revision(root: Path) -> tuple[str, str]:
    """Use actual Git metadata, or a validated immutable Octopus source-archive SHA."""
    if (root / ".git").exists():
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=False, capture_output=True, text=True
        )
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=root, check=False, capture_output=True, text=True
        )
        if commit.returncode == 0 and branch.returncode == 0:
            return commit.stdout.strip(), branch.stdout.strip()
    archive_sha = os.getenv("LIVE_EXPECTED_SHA", "").strip()
    if not re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", archive_sha):
        raise RuntimeError("source revision unavailable: valid Git or Octopus commit SHA required")
    return archive_sha, "octopus-release-archive"


def make_fixture(base: Path) -> Path:
    root = base / "fixture"
    (root / "apps/api/src/dual_lineage").mkdir(parents=True)
    (root / "apps/api/tests").mkdir(parents=True)
    (root / "apps/sandbox_worker").mkdir(parents=True)
    (root / "apps/sandbox_worker/__init__.py").write_text("")
    (root / "apps/api/src/dual_lineage/__init__.py").write_text("")
    (root / CALC_PATH).write_text(FIXTURE_CALC)
    (root / TEST_PATH).write_text(FIXTURE_TEST)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "e2e@example.invalid")
    _git(root, "config", "user.name", "devpilot-e2e")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture with a planted bug")
    return root


def _redacted_database(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.hostname}:{parts.port or 5432}/{parts.path.lstrip('/')}"


class _Process:
    """Everything one API process would build. A new instance shares nothing in memory."""

    def __init__(self, database_url: str, root: Path, worktrees: Path, *, enable_patch: bool) -> None:
        self.spine_store = PostgresSpineStore(database_url)
        self.spine = SharedSpine(self.spine_store)
        self.tasks = DevTaskService(PostgresDevTaskStore(database_url))
        self.undermind = DeterministicUndermind(autopilot_policy(enable_patch=enable_patch))
        registry = ActionRegistry()
        registry.register(FileInspectExecutor((root,)))
        register_dev_tools(registry, root=root, worktrees=worktrees)
        register_patch_tools(registry, root=root, worktrees=worktrees, task_store=self.tasks.store)
        self.gateway = ActionGateway(undermind=self.undermind, registry=registry, spine=self.spine)


async def run_e2e(database_url: str, *, artifact_dir: Path | None) -> dict[str, Any]:
    apply_migrations(database_url)
    started = datetime.now(UTC)
    source_commit, source_branch = _source_revision(ROOT)
    checks: dict[str, bool] = {}
    details: dict[str, Any] = {}
    snapshot_before = _checkout_snapshot(ROOT)
    requests_before = set(PostgresSpineStore(database_url).request_ids())

    with tempfile.TemporaryDirectory(prefix="devpilot-e2e-") as tmp:
        base = Path(tmp)
        root = make_fixture(base)
        worktrees = base / "worktrees"
        fixture_head = _git(root, "rev-parse", "HEAD").strip()

        # 1. Detect: a real pytest run of the fixture, ingested as a CI failure.
        junit = base / "junit.xml"
        run = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "pytest", "-q", "-rfE", "-p", "no:cacheprovider",
             f"--junitxml={junit}", "tests"],
            cwd=root / "apps/api", env={**os.environ, "PYTHONPATH": str(root / "apps/api/src")},
            capture_output=True, text=True, check=False,
        )
        first = _Process(database_url, root, worktrees, enable_patch=False)
        ingested = CIIngestor(first.tasks).ingest(CIFailureReport(
            source="pytest", repository="fixture/devpilot-e2e", branch="main", commit_sha=fixture_head,
            job="e2e-fixture", log=run.stdout, junit_xml=junit.read_text(),
        ))
        task_id = ingested.task_id
        task = first.tasks.store.task(task_id)
        checks["1_failure_detected"] = run.returncode == 1 and bool(ingested.failures)
        checks["2_task_created"] = task.state is TaskState.TRIAGED and task.spec.source == "ci"
        checks["3_evidence_recorded"] = all(
            task.latest(kind) is not None
            for kind in (EvidenceKind.CI_RESULT, EvidenceKind.TEST_RESULT, EvidenceKind.DIAGNOSIS)
        )
        checks["class_c_stops_for_approval"] = (
            ingested.next_step == "awaiting_human_approval"
            and [b.blocker_id for b in task.open_blockers] == ["awaiting-approval"]
        )

        # 2. Diagnose (the operator confirms this one test run).
        diagnosis, _ = await run_diagnosis(
            gateway=first.gateway, undermind=first.undermind, spine=first.spine,
            issue=IssueInput(description="test_add fails in CI", test_ids=(FAILING,)),
            confirm_test_run=True,
        )
        first.tasks.record_evidence(task_id, EvidenceKind.DIAGNOSIS, diagnosis.likely_root_cause[:1_900],
                                    actor=Actor.AUTOPILOT, data={"risk": diagnosis.risk.value})
        checks["4_diagnosis_produced"] = (
            diagnosis.root_cause_basis == "test_failure_trace"
            and f"{CALC_PATH}:2" in diagnosis.likely_root_cause
            and not diagnosis.files_modified
        )
        details["diagnosis_network_isolated"] = not any(
            "without network isolation" in item for item in diagnosis.uncertainty
        )

        # 3. Investigate, propose, and approve (approval by this harness as the operator).
        tasks = first.tasks
        tasks.transition(task_id, TaskState.INVESTIGATED, actor=Actor.AUTOPILOT, reason="diagnosed")
        tasks.declare_scope(task_id, [CALC_PATH, TEST_PATH], actor=Actor.AUTOPILOT,
                            proposed_actions=["patch.apply_scoped calc.py + regression test"])
        tasks.transition(task_id, TaskState.PROPOSED, actor=Actor.AUTOPILOT, reason="fix proposed")
        tasks.record_approval(task_id, Approval(kind=ApprovalKind.CHANGE, approver="e2e-operator",
                                                risk=RiskClass.C), actor=Actor.HUMAN)
        tasks.clear_blocker(task_id, "awaiting-approval", actor=Actor.HUMAN)
        tasks.transition(task_id, TaskState.APPROVED, actor=Actor.HUMAN, reason="operator approved")

        # 4. A patch attempt that fails its tests...
        patcher = _Process(database_url, root, worktrees, enable_patch=True)
        failed = await prepare_patch(
            gateway=patcher.gateway, undermind=patcher.undermind, spine=patcher.spine, tasks=patcher.tasks,
            request=PatchRequest(task_id=task_id, edits=(WRONG_FIX, TEST_EDIT), test_ids=(TEST_PATH,)),
            confirm_writes=True, confirm_test_run=True,
        )
        checks["failed_attempt_stays_in_implementation"] = (
            failed.final_state is TaskState.IMPLEMENTED and failed.tests_failed > 0
        )

        # ...then a restart: brand-new objects that share nothing with the first process.
        resumed = _Process(database_url, root, worktrees, enable_patch=True)
        checks["9_interrupted_work_resumed"] = (
            resumed.tasks.store.task(task_id).state is TaskState.IMPLEMENTED
        )
        report = await prepare_patch(
            gateway=resumed.gateway, undermind=resumed.undermind, spine=resumed.spine, tasks=resumed.tasks,
            request=PatchRequest(task_id=task_id, edits=(RIGHT_FIX, TEST_EDIT_2), test_ids=(TEST_PATH,)),
            confirm_writes=True, confirm_test_run=True,
        )
        checks["5_patch_prepared"] = bool(report.changed_files) and report.worktree is not None
        checks["6_focused_tests_pass"] = report.tests_failed == 0 and report.tests_passed >= 3
        checks["8_task_reached_review_requested"] = report.final_state is TaskState.REVIEW_REQUESTED

        # 5. Review package; automatic merge must refuse.
        final = resumed.tasks.store.task(task_id)
        package = build_review_package(final, report)
        eligibility = auto_merge_eligibility(final, package, unresolved_review_findings=0)
        body = render_markdown(package, eligibility)
        checks["7_diff_is_reviewable"] = (
            "+    return a + b" in report.diff and "### Changed files" in body
        )
        checks["merge_refused"] = merge_allowed(eligibility)[0] is False

        # 6. Forbidden-action audit from the PostgreSQL Spine, plus one attempted bypass.
        allowed = enabled_tools(enable_patch=True)
        attempt = resumed.undermind.preflight(
            PreflightRequest(request_id=f"devpilot-e2e-bypass-{task_id}", requested_tools=frozenset({"shell.exec"}))
        )
        resumed.spine.begin(attempt.envelope.request_id)
        resumed.spine.record_preflight(attempt)
        bypass = await resumed.gateway.execute(
            attempt.envelope,
            ActionCall(intent=ActionIntent(action_id="bypass", tool_name="shell.exec", kind=ActionKind.EXECUTE),
                       arguments={"command": "touch /tmp/devpilot-e2e-pwned"}, confirmed=True),
        )
        used: set[str] = set()
        completed: set[str] = set()
        for request_id in resumed.spine_store.request_ids():
            if not request_id.startswith(("devpilot-diag-", "devpilot-patch-", "devpilot-e2e-bypass-")):
                continue
            for event in resumed.spine_store.events(request_id):
                if event.kind is EventKind.ACTION_PROPOSED and event.tool_name:
                    used.add(event.tool_name)
                if event.kind is EventKind.ACTION_COMPLETED and event.tool_name:
                    completed.add(event.tool_name)
        checks["10_no_forbidden_action_executed"] = (
            bypass.status is ActionRunStatus.DENIED
            and not completed & FORBIDDEN_TOOLS
            and completed <= allowed
            and not Path("/tmp/devpilot-e2e-pwned").exists()
            and _git(root, "rev-parse", "HEAD").strip() == fixture_head
            and _git(root, "rev-list", "--count", "--all").strip() == "1"
        )
        details.update({
            "task_id": task_id,
            "final_state": final.state.value,
            "tools_proposed": sorted(used),
            "tools_completed": sorted(completed),
            "forbidden_attempt": f"shell.exec -> {bypass.status.value}",
            "risk": final.risk.value,
            "transitions": [record.to_state.value for record in final.transitions],
            "evidence_records": len(final.evidence),
            "tests_after_fix": {"passed": report.tests_passed, "failed": report.tests_failed},
            "merge_eligibility_failed": list(eligibility.failed),
            "network_isolation_available": await NetworkSandbox.available(),
        })
        # Fail closed: a source archive without .git is compared by content hash instead.
        checks["main_checkout_untouched"] = _checkout_snapshot(ROOT) == snapshot_before
        details["source_checkout_audit"] = snapshot_before[0]

    # Exactly the Spine requests this run created, so a test harness can remove only its own rows.
    details["spine_request_ids"] = sorted(set(PostgresSpineStore(database_url).request_ids()) - requests_before)
    with PostgresSpineStore(database_url)._connect() as connection:
        server_version = connection.execute("SHOW server_version").fetchone()[0]
    result = {
        "evidence": "devpilot-e2e",
        "kind": "local functional E2E (library-level; no HTTP route exists for the autopilot)",
        "commit_sha": source_commit,
        "branch": source_branch,
        # False means the run used uncommitted code, so commit_sha alone does not describe it.
        # None means a source archive: there is no git status to compare against.
        "worktree_clean": snapshot_before[1] == "" if snapshot_before[0] == "git" else None,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "database": _redacted_database(database_url),
        "postgres_server_version": server_version,
        "approval_actor": "the E2E harness acting as the human operator (not a real person)",
        "checks": checks,
        "passed": all(checks.values()),
        "details": details,
        "not_covered": [
            "CI and live environments (this is local evidence)",
            "a real human review",
            "an HTTP/API route: the autopilot is not wired into the runtime",
        ],
    }
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    for line in text.splitlines():
        reject_secrets(line)  # the artifact must not carry a credential
    if artifact_dir is not None:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        stamp = started.strftime("%Y%m%dT%H%M%SZ")
        (artifact_dir / f"e2e-{stamp}.json").write_text(text)
        result["artifact"] = str((artifact_dir / f"e2e-{stamp}.json").relative_to(ROOT))
    return result


def main() -> int:
    database_url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not database_url:
        print("ERROR: TEST_DATABASE_URL is required; this E2E runs only against real PostgreSQL.")
        return 2
    result = asyncio.run(run_e2e(database_url, artifact_dir=ROOT / "artifacts" / "devpilot"))
    for name, ok in sorted(result["checks"].items()):
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print(f"artifact: {result.get('artifact')}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
