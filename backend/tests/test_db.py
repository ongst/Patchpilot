from pathlib import Path

from patchpilot.db import RunStore
from patchpilot.models import RunRecord, RunStatus


def test_run_store_round_trip_and_events(tmp_path: Path):
    store = RunStore(tmp_path / "runs.sqlite3")
    run = RunRecord(
        run_id="abc123",
        status=RunStatus.QUEUED,
        repo_url="https://github.com/example/repo",
        issue_text="A sufficiently detailed issue",
    )
    store.create_run(run)
    assert store.get_run("abc123") == run

    updated = store.set_status("abc123", RunStatus.PLANNING, "Planning")
    assert updated.status == RunStatus.PLANNING
    events = store.get_events("abc123")
    assert events[0].message == "Planning"


def test_terminal_status_sets_finish_time(tmp_path: Path):
    store = RunStore(tmp_path / "runs.sqlite3")
    store.create_run(
        RunRecord(
            run_id="done",
            status=RunStatus.QUEUED,
            repo_url="https://github.com/example/repo",
            issue_text="A sufficiently detailed issue",
        )
    )
    completed = store.set_status("done", RunStatus.COMPLETED)
    assert completed.finished_at is not None
