from fastapi.testclient import TestClient
from patchpilot.config import get_settings


def test_health_and_missing_run(tmp_path, monkeypatch):
    monkeypatch.setenv("PATCHPILOT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PATCHPILOT_WORKSPACE_DIR", str(tmp_path / "workspaces"))
    monkeypatch.setenv("PATCHPILOT_DOCKER_ENABLED", "false")
    monkeypatch.setenv("PATCHPILOT_LLM_API_KEY", "")
    get_settings.cache_clear()
    import patchpilot.main as main_module

    main_module.app.state.workflow.close()
    app = main_module.create_app()

    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["database"] is True
        assert response.json()["status"] == "degraded"

        missing = client.get("/api/runs/does-not-exist")
        assert missing.status_code == 404

        invalid = client.post(
            "/api/runs",
            json={
                "repo_url": "https://example.com/not/github",
                "issue_text": "This issue description is long enough",
            },
        )
        assert invalid.status_code == 422
    get_settings.cache_clear()
