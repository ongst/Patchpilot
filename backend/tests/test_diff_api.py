from fastapi.testclient import TestClient
from patchpilot.config import get_settings
from patchpilot.models import RunRecord, RunStatus


def _diff_client(tmp_path, monkeypatch):
    monkeypatch.setenv("PATCHPILOT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PATCHPILOT_WORKSPACE_DIR", str(tmp_path / "workspaces"))
    get_settings.cache_clear()
    import patchpilot.main as main_module

    main_module.app.state.workflow.close()
    app = main_module.create_app()
    return app, TestClient(app)


def _seed_run(app, run_id: str, patch: str):
    app.state.store.create_run(
        RunRecord(
            run_id=run_id,
            status=RunStatus.COMPLETED,
            repo_url="https://github.com/owner/repo",
            issue_text="just a test issue",
            patch=patch,
        )
    )


PATCH = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
"""


def test_diff_returns_stats(tmp_path, monkeypatch):
    app, client = _diff_client(tmp_path, monkeypatch)
    with client:
        _seed_run(app, "run-1", PATCH)
        body = client.get("/api/runs/run-1/diff").json()
    assert body["files"] == [{"path": "app.py", "additions": 1, "deletions": 1}]
    assert body["additions"] == 1
    assert body["deletions"] == 1
    assert body["changed_lines"] == 2


def test_diff_empty_patch(tmp_path, monkeypatch):
    app, client = _diff_client(tmp_path, monkeypatch)
    with client:
        _seed_run(app, "run-1", "")
        body = client.get("/api/runs/run-1/diff").json()
    assert body["files"] == []
    assert body["additions"] == 0
    assert body["deletions"] == 0
    assert body["changed_lines"] == 0


def test_diff_missing_run(tmp_path, monkeypatch):
    _, client = _diff_client(tmp_path, monkeypatch)
    with client:
        response = client.get("/api/runs/missing/diff")
    assert response.status_code == 404
