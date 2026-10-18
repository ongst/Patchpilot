from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from langgraph.types import Command
from patchpilot.config import Settings
from patchpilot.db import RunStore
from patchpilot.git_service import GitService
from patchpilot.llm import ProposalResult, RepairProposal
from patchpilot.models import ApprovalStage, RepairPlan, RunRecord, RunStatus, TestResult
from patchpilot.reporting import build_run_report
from patchpilot.workflow import WorkflowEngine

FIXTURE = Path(__file__).parents[2] / "eval" / "fixtures" / "python_calculator"


class FakeLLM:
    """固定返回一个确定性的 RepairProposal，不访问真实模型。"""

    def __init__(self, settings: Settings):
        self.settings = settings

    def propose(self, tools, issue_text, language, test_result, current_diff, attempt):
        plan = RepairPlan(
            summary="Fix add() to add instead of subtract",
            root_cause="add() returns a - b instead of a + b",
            steps=["Change return a - b to return a + b"],
            tests=["python -m pytest -q"],
            risks=[],
        )
        patch = """diff --git a/calculator.py b/calculator.py
--- a/calculator.py
+++ b/calculator.py
@@ -1,2 +1,2 @@
 def add(a: int, b: int) -> int:
-    return a - b
+    return a + b
"""
        return ProposalResult(
            proposal=RepairProposal(plan=plan, patch=patch),
            inspected_files=["calculator.py"],
            token_usage=2840,
        )


class FakeRunner:
    """按 phase 返回固定测试结果：baseline 失败、post_patch 通过，并记录调用。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.calls: list[str] = []

    def run(self, repo, language, requested_command, phase):
        self.calls.append(phase)
        if phase == "baseline":
            return TestResult(
                command="python -m pytest -q", passed=False, phase="baseline",
                output="assert -1 == 5",
            )
        return TestResult(
            command="python -m pytest -q", passed=True, phase=phase, output="",
        )


class FakeGit(GitService):
    """替换网络边界，但保留真实的 git apply / diff（安全核心链路）。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.commit_called = False
        self.push_called = False

    def clone_and_branch(self, repo_url, destination, run_id):
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            FIXTURE,
            destination,
            ignore=shutil.ignore_patterns(".pytest_cache", "__pycache__", "*.pyc"),
        )
        subprocess.run(["git", "init", "-b", "main"], cwd=destination, check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=destination, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=t@e.com", "commit", "-m", "init"],
            cwd=destination, check=True, capture_output=True,
        )
        branch = f"patchpilot/run-{run_id[:8]}"
        subprocess.run(["git", "switch", "-c", branch], cwd=destination, check=True, capture_output=True)
        return branch

    def commit(self, repo, run_id):
        self.commit_called = True
        return "fake-sha-12345678"

    def push(self, repo):
        self.push_called = True
        return "patchpilot/run-fake"


def test_golden_path_local_completion(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path / "data", workspace_dir=tmp_path / "workspaces")
    store = RunStore(settings.database_path)
    run = RunRecord(
        run_id="12345678abcdef00",
        status=RunStatus.QUEUED,
        repo_url="https://github.com/example/demo",
        issue_text="add(a, b) incorrectly subtracts b instead of adding it",
        test_command="python -m pytest -q",
    )
    store.create_run(run)

    monkeypatch.setattr("patchpilot.workflow.GitService", FakeGit)
    monkeypatch.setattr("patchpilot.workflow.DockerTestRunner", FakeRunner)
    monkeypatch.setattr("patchpilot.workflow.RepairLLM", FakeLLM)
    workflow = WorkflowEngine(settings, store)

    config = workflow.config_for(run.run_id)
    initial_state = {
        "run_id": run.run_id,
        "repo_url": run.repo_url,
        "issue_text": run.issue_text,
        "test_command": run.test_command,
        "attempt_count": 0,
        "token_usage": 0,
    }

    # 第一次调用：跑到补丁审批暂停
    workflow.graph.invoke(initial_state, config=config)
    after_patch_approval = store.get_run(run.run_id)
    assert after_patch_approval.status == RunStatus.AWAITING_PATCH_APPROVAL
    assert after_patch_approval.approval_stage == ApprovalStage.APPLY_PATCH
    assert after_patch_approval.patch
    assert after_patch_approval.repair_plan is not None

    # 第二次调用：批准补丁，跑到推送审批暂停
    workflow.graph.invoke(Command(resume={"approved": True}), config=config)
    after_push_approval = store.get_run(run.run_id)
    assert after_push_approval.status == RunStatus.AWAITING_PUSH_APPROVAL
    assert after_push_approval.approval_stage == ApprovalStage.PUSH_BRANCH
    assert after_push_approval.test_result is not None and after_push_approval.test_result.passed

    # 验证补丁真正改动了工作区文件
    workspace_file = settings.workspace_dir / run.run_id / "repo" / "calculator.py"
    content = workspace_file.read_text(encoding="utf-8")
    assert "return a + b" in content
    assert "return a - b" not in content

    # 第三次调用：拒绝推送，流程结束
    workflow.graph.invoke(Command(resume={"approved": False}), config=config)
    final = store.get_run(run.run_id)
    assert final.status == RunStatus.COMPLETED_LOCAL
    assert final.remote_branch == ""
    assert final.commit_sha == ""

    # 黄金路径不应该调用 commit / push
    git = workflow.git
    assert git.commit_called is False
    assert git.push_called is False
    assert workflow.runner.calls == ["baseline", "post_patch"]

    # 最终报告与文件、测试、状态一致
    report = build_run_report(final)
    assert report.status == RunStatus.COMPLETED_LOCAL
    assert [f.path for f in report.changed_files] == ["calculator.py"]
    assert report.additions == 1
    assert report.deletions == 1
    assert report.attempt_count == 1
    assert report.baseline_result is not None and report.baseline_result.passed is False
    assert report.test_result is not None and report.test_result.passed is True
    assert report.token_usage == 2840

    # 关键状态事件顺序（LangGraph 恢复会重跑 interrupt 节点，去重后断言首次出现顺序）
    statuses = [e.data.get("status") for e in store.get_events(run.run_id) if e.event_type == "status"]
    unique_statuses = list(dict.fromkeys(statuses))
    assert unique_statuses == [
        "cloning",
        "profiling",
        "baseline_testing",
        "planning",
        "validating_patch",
        "awaiting_patch_approval",
        "applying_patch",
        "testing",
        "awaiting_push_approval",
        "completed_local",
    ]

    workflow.close()
