from fastapi.testclient import TestClient
from patchpilot.config import get_settings
from patchpilot.models import RunRecord, RunStatus


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("PATCHPILOT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PATCHPILOT_WORKSPACE_DIR", str(tmp_path / "workspaces"))
    get_settings.cache_clear()
    import patchpilot.main as main_module
    main_module.app.state.workflow.close()
    app = main_module.create_app()
    return app, TestClient(app)


def _seed(app, run_id: str, status: RunStatus):
    app.state.store.create_run(RunRecord(
        run_id=run_id, status=status,
        repo_url="https://github.com/owner/repo", issue_text="just a test issue",
    ))


def test_cancel_missing_run(tmp_path, monkeypatch):
    _, client = _client(tmp_path, monkeypatch)
    with client:
        response = client.post("/api/runs/missing/cancel")
    assert response.status_code == 404


def test_cancel_running_run(tmp_path, monkeypatch):
    app, client = _client(tmp_path, monkeypatch)
    with client:
        _seed(app, "run-1", RunStatus.QUEUED)
        body = client.post("/api/runs/run-1/cancel").json()
    assert body["status"] == "cancelled"
    assert body["finished_at"] is not None


def test_cancel_terminal_is_idempotent(tmp_path, monkeypatch):
    app, client = _client(tmp_path, monkeypatch)
    with client:
        _seed(app, "run-1", RunStatus.COMPLETED)
        body = client.post("/api/runs/run-1/cancel").json()
    assert body["status"] == "completed"
