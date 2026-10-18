import json

from fastapi.testclient import TestClient
from patchpilot.config import get_settings
from patchpilot.models import RunRecord, RunStatus


def _report_client(tmp_path, monkeypatch):
    monkeypatch.setenv("PATCHPILOT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PATCHPILOT_WORKSPACE_DIR", str(tmp_path / "workspaces"))
    get_settings.cache_clear()
    import patchpilot.main as main_module

    main_module.app.state.workflow.close()
    app = main_module.create_app()
    return app, TestClient(app)


def _seed_run(app, run_id: str, status: RunStatus):
    app.state.store.create_run(
        RunRecord(
            run_id=run_id,
            status=status,
            repo_url="https://github.com/owner/repo",
            issue_text="just a test issue",
        )
    )


def test_report_missing_run(tmp_path, monkeypatch):
    _, client = _report_client(tmp_path, monkeypatch)
    with client:
        response = client.get("/api/runs/missing/report")
    assert response.status_code == 404


def test_report_non_terminal_conflict(tmp_path, monkeypatch):
    app, client = _report_client(tmp_path, monkeypatch)
    with client:
        _seed_run(app, "run-1", RunStatus.PLANNING)
        response = client.get("/api/runs/run-1/report")
    assert response.status_code == 409


def test_report_terminal_returns_report(tmp_path, monkeypatch):
    app, client = _report_client(tmp_path, monkeypatch)
    with client:
        _seed_run(app, "run-1", RunStatus.COMPLETED)
        body = client.get("/api/runs/run-1/report").json()
    assert body["status"] == "completed"
    assert body["run_id"] == "run-1"


def test_report_has_no_secrets(tmp_path, monkeypatch):
    app, client = _report_client(tmp_path, monkeypatch)
    with client:
        _seed_run(app, "run-1", RunStatus.COMPLETED)
        body = client.get("/api/runs/run-1/report").json()
    text = json.dumps(body)
    for key in ("llm_api_key", "github_token", "authorization"):
        assert key not in text
