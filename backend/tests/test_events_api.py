from fastapi.testclient import TestClient
from patchpilot.config import get_settings
from patchpilot.models import RunRecord, RunStatus


def _event_client(tmp_path, monkeypatch):
    monkeypatch.setenv("PATCHPILOT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PATCHPILOT_WORKSPACE_DIR", str(tmp_path / "workspaces"))
    get_settings.cache_clear()
    import patchpilot.main as main_module

    main_module.app.state.workflow.close()
    app = main_module.create_app()
    return app, TestClient(app)


def _seed(app, run_id: str, status: RunStatus, count: int):
    store = app.state.store
    run = RunRecord(
        run_id=run_id,
        status=status,
        repo_url="https://github.com/owner/repo",
        issue_text="just a test issue",
    )
    store.create_run(run)
    for i in range(1, count + 1):
        store.add_event(run_id, "info", "status", f"event {i}")


def test_events_missing_run(tmp_path, monkeypatch):
    _, client = _event_client(tmp_path, monkeypatch)
    with client:
        response = client.get("/api/runs/missing/events")
    assert response.status_code == 404


def test_events_after_cursor(tmp_path,monkeypatch):
    app, client = _event_client(tmp_path, monkeypatch)
    with client:
        _seed(app, "run-1", RunStatus.COMPLETED, 3)
        response = client.get("/api/runs/run-1/events?after=1")
        ids = []
        for line in response.text.splitlines():
            if line.startswith("id: "):
                ids.append(int(line.removeprefix("id: ")))
    assert ids == [2, 3]


def test_events_last_event_id(tmp_path, monkeypatch):
    app, client = _event_client(tmp_path, monkeypatch)
    with client:
        _seed(app, "run-2", RunStatus.COMPLETED, 3)
        response = client.get("/api/runs/run-2/events", headers={"Last-Event-ID": "2"})
        ids = []
        for line in response.text.splitlines():
            if line.startswith("id: "):
                ids.append(int(line.removeprefix("id: ")))
    assert ids == [3]


def test_events_end(tmp_path, monkeypatch):
    app, client = _event_client(tmp_path, monkeypatch)
    with client:
        _seed(app, "run-3", RunStatus.CANCELLED, 2)
        response = client.get("/api/runs/run-3/events")
        ids = []
        for line in response.text.splitlines():
            if line.startswith("id: "):
                ids.append(int(line.removeprefix("id: ")))
    assert ids == [1, 2]
    assert "event: end" in response.text

