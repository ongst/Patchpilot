from patchpilot.db import RunStore
from patchpilot.main import recover_interrupted_runs
from patchpilot.models import RunRecord, RunStatus


def _seed(store, run_id: str, status: RunStatus):
    store.create_run(RunRecord(
        run_id=run_id, status=status,
        repo_url="https://github.com/owner/repo", issue_text="just a test issue",
    ))


def test_recovery_keeps_approval_waiting(tmp_path):
    store = RunStore(tmp_path / "db.sqlite3")
    _seed(store, "run-1", RunStatus.AWAITING_PATCH_APPROVAL)
    _seed(store, "run-2", RunStatus.AWAITING_PUSH_APPROVAL)
    recover_interrupted_runs(store)
    assert store.get_run("run-1").status == RunStatus.AWAITING_PATCH_APPROVAL
    assert store.get_run("run-2").status == RunStatus.AWAITING_PUSH_APPROVAL


def test_recovery_marks_running_failed(tmp_path):
    store = RunStore(tmp_path / "db.sqlite3")
    _seed(store, "run-1", RunStatus.PLANNING)
    recover_interrupted_runs(store)
    run = store.get_run("run-1")
    assert run.status == RunStatus.FAILED
    assert run.error != ""
    assert any(e.event_type == "recovery" for e in store.get_events("run-1"))


def test_recovery_keeps_terminal(tmp_path):
    store = RunStore(tmp_path / "db.sqlite3")
    _seed(store, "run-1", RunStatus.COMPLETED)
    recover_interrupted_runs(store)
    assert store.get_run("run-1").status == RunStatus.COMPLETED
