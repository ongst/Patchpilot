import json
import shutil

from fastapi.testclient import TestClient
from patchpilot.config import get_settings
from patchpilot.test_runner import DockerTestRunner


def _assert_no_secrets(body: dict) -> None:
    """断言健康响应不包含任何密钥字段。"""
    for key in ("token", "github_token", "api_key", "llm_api_key"):
        assert key not in body


def _health_client(tmp_path, monkeypatch, *, llm_key: str, github_token: str):
    """构建健康检查用的 TestClient，并把 git/docker 强制置为可用。"""
    monkeypatch.setenv("PATCHPILOT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PATCHPILOT_WORKSPACE_DIR", str(tmp_path / "workspaces"))
    monkeypatch.setenv("PATCHPILOT_DOCKER_ENABLED", "true")
    monkeypatch.setenv("PATCHPILOT_LLM_API_KEY", llm_key)
    monkeypatch.setenv("PATCHPILOT_GITHUB_TOKEN", github_token)
    get_settings.cache_clear()

    # 绕过真实的 `docker info` 子进程，避免依赖宿主机守护进程
    monkeypatch.setattr(DockerTestRunner, "available", lambda self: True)

    # 让 `shutil.which("git")` 确定性地命中，其余命令仍走真实实现
    real_which = shutil.which
    monkeypatch.setattr(
        shutil, "which",
        lambda cmd, *args, **kwargs: "/usr/bin/git" if cmd == "git" else real_which(cmd, *args, **kwargs),
    )

    import patchpilot.main as main_module

    main_module.app.state.workflow.close()
    app = main_module.create_app()
    return TestClient(app)


def test_health_and_missing_run(tmp_path, monkeypatch):
    # 用例 1：基础依赖缺失（docker 关闭、LLM 未配置）→ degraded
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
        body = response.json()
        assert body["database"] is True
        assert body["status"] == "degraded"
        assert body["ready_for_repair"] is False
        assert body["ready_for_push"] is False
        _assert_no_secrets(body)

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


def test_health_ready_without_token(tmp_path, monkeypatch):
    # 用例 2：基础依赖正常、GitHub Token 为空 → 可修复但不可推送
    with _health_client(tmp_path, monkeypatch, llm_key="sk-test", github_token="") as client:
        body = client.get("/api/health").json()

    assert body["status"] == "ok"
    assert body["database"] is True
    assert body["git"] is True
    assert body["docker"] is True
    assert body["llm_configured"] is True
    assert body["ready_for_repair"] is True
    assert body["ready_for_push"] is False
    _assert_no_secrets(body)


def test_health_ready_with_token(tmp_path, monkeypatch):
    # 用例 3：基础依赖正常、GitHub Token 存在 → 可修复且可推送
    fake_token = "ghp_fakeToken000000000000000000000000"
    with _health_client(tmp_path, monkeypatch, llm_key="sk-test", github_token=fake_token) as client:
        body = client.get("/api/health").json()

    assert body["status"] == "ok"
    assert body["ready_for_repair"] is True
    assert body["ready_for_push"] is True
    _assert_no_secrets(body)
    # 假 token 内容绝不能出现在响应里
    assert fake_token not in json.dumps(body)
