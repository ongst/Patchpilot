from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from patchpilot.config import Settings
from patchpilot.db import RunStore
from patchpilot.git_service import GitService
from patchpilot.llm import RepairLLM
from patchpilot.models import ApprovalStage, Language, RunStatus, TestResult
from patchpilot.patching import validate_patch
from patchpilot.repo_tools import RepositoryTools
from patchpilot.test_runner import DockerTestRunner


class RunCancelledError(RuntimeError):
    """用户取消任务后，在工作流安全点抛出的专用异常。"""


class WorkflowState(TypedDict, total=False):
    run_id: str
    repo_url: str
    issue_text: str
    test_command: str | None
    workspace: str
    branch_name: str
    language: str
    repair_plan: dict[str, Any]
    inspected_files: list[str]
    patch: str
    attempt_count: int
    baseline_result: dict[str, Any]
    test_result: dict[str, Any]
    token_usage: int
    approved: bool
    push_approved: bool
    rejected_stage: str
    commit_sha: str
    remote_branch: str
    error: str


class WorkflowEngine:
    def __init__(self, settings: Settings, store: RunStore):
        self.settings = settings
        self.store = store
        self.git = GitService(
            settings.github_token,
            settings.git_author_name,
            settings.git_author_email,
        )
        self.runner = DockerTestRunner(settings)
        self.llm = RepairLLM(settings)
        self._checkpoint_connection = sqlite3.connect(
            settings.checkpoint_path,
            check_same_thread=False,
        )
        self.checkpointer = SqliteSaver(self._checkpoint_connection)
        self.graph = self._build_graph().compile(checkpointer=self.checkpointer)

    def close(self) -> None:
        self._checkpoint_connection.close()

    def config_for(self, run_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": run_id}}

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(WorkflowState)
        graph.add_node("prepare", self._prepare)
        graph.add_node("baseline", self._baseline)
        graph.add_node("propose", self._propose)
        graph.add_node("validate", self._validate)
        graph.add_node("approve_patch", self._approve_patch)
        graph.add_node("apply", self._apply)
        graph.add_node("test", self._test)
        graph.add_node("approve_push", self._approve_push)
        graph.add_node("commit_push", self._commit_push)
        graph.add_node("reject", self._reject)
        graph.add_node("fail", self._fail)

        graph.add_edge(START, "prepare")
        graph.add_edge("prepare", "baseline")
        graph.add_edge("baseline", "propose")
        graph.add_edge("propose", "validate")
        graph.add_edge("validate", "approve_patch")
        graph.add_conditional_edges(
            "approve_patch",
            lambda state: "apply" if state.get("approved") else "reject",
            {"apply": "apply", "reject": "reject"},
        )
        graph.add_edge("apply", "test")
        graph.add_conditional_edges(
            "test",
            self._route_after_test,
            {"retry": "propose", "push": "approve_push", "fail": "fail"},
        )
        graph.add_conditional_edges(
            "approve_push",
            lambda state: "push" if state.get("push_approved") else "local",
            {"push": "commit_push", "local": END},
        )
        graph.add_edge("commit_push", END)
        graph.add_edge("reject", END)
        graph.add_edge("fail", END)
        return graph

    def _ensure_active(self, run_id: str) -> None:
        run = self.store.get_run(run_id)
        if run is None:
            raise RuntimeError("Run record disappeared")
        if run.status == RunStatus.CANCELLED:
            raise RunCancelledError(run_id)


    def _status(self, run_id: str, status: RunStatus, message: str) -> None:
        self._ensure_active(run_id)
        self.store.set_status(run_id, status, message)

    def _prepare(self, state: WorkflowState) -> dict[str, Any]:
        run_id = state["run_id"]
        self._status(run_id, RunStatus.CLONING, "正在克隆公开仓库并创建隔离分支")
        workspace = self.settings.workspace_dir / run_id / "repo"
        branch = self.git.clone_and_branch(state["repo_url"], workspace, run_id)
        self._status(run_id, RunStatus.PROFILING, "正在识别项目语言、清单和测试结构")
        tools = RepositoryTools(
            workspace, self.settings.max_file_bytes, self.settings.max_tool_output_chars
        )
        profile = tools.profile()
        language = Language(str(profile["language"]))
        if language == Language.UNKNOWN:
            raise RuntimeError(
                "Repository does not contain a supported Python or JavaScript project"
            )
        self.store.update_run(
            run_id,
            workspace=str(workspace),
            branch_name=branch,
            language=language,
            started_at=datetime.now(UTC),
        )
        self.store.add_event(run_id, "info", "profile", "仓库画像完成", profile)
        return {"workspace": str(workspace), "branch_name": branch, "language": language.value}

    def _baseline(self, state: WorkflowState) -> dict[str, Any]:
        run_id = state["run_id"]
        self._status(run_id, RunStatus.BASELINE_TESTING, "正在运行基线测试")
        result = self.runner.run(
            Path(state["workspace"]),
            Language(state["language"]),
            state.get("test_command"),
            "baseline",
        )
        self._ensure_active(run_id)
        self.store.update_run(run_id, baseline_result=result)
        self.store.add_event(
            run_id,
            "info" if result.passed else "warning",
            "test",
            "基线测试完成" if not result.skipped_reason else result.skipped_reason,
            result.model_dump(),
        )
        return {"baseline_result": result.model_dump()}

    def _propose(self, state: WorkflowState) -> dict[str, Any]:
        run_id = state["run_id"]
        attempt = int(state.get("attempt_count", 0)) + 1
        status = RunStatus.PLANNING if attempt == 1 else RunStatus.REPAIRING
        self._status(run_id, status, f"Agent 正在分析代码并生成第 {attempt} 版补丁")
        workspace = Path(state["workspace"])
        tools = RepositoryTools(
            workspace, self.settings.max_file_bytes, self.settings.max_tool_output_chars
        )
        latest_result = state.get("test_result") or state.get("baseline_result")
        proposal = self.llm.propose(
            tools,
            state["issue_text"],
            state["language"],
            TestResult.model_validate(latest_result) if latest_result else None,
            self.git.diff(workspace),
            attempt,
        )
        self._ensure_active(run_id)
        total_tokens = int(state.get("token_usage", 0)) + proposal.token_usage
        plan = proposal.proposal.plan.model_dump()
        self.store.update_run(
            run_id,
            repair_plan=plan,
            inspected_files=proposal.inspected_files,
            patch=proposal.proposal.patch,
            attempt_count=attempt,
            token_usage=total_tokens,
        )
        self.store.add_event(
            run_id,
            "info",
            "proposal",
            f"第 {attempt} 版修复方案已生成",
            {"plan": plan, "inspected_files": proposal.inspected_files},
        )
        return {
            "repair_plan": plan,
            "inspected_files": proposal.inspected_files,
            "patch": proposal.proposal.patch,
            "attempt_count": attempt,
            "token_usage": total_tokens,
            "approved": False,
        }

    def _validate(self, state: WorkflowState) -> dict[str, Any]:
        run_id = state["run_id"]
        self._status(run_id, RunStatus.VALIDATING_PATCH, "正在执行补丁路径、规模与 Git 校验")
        summary = validate_patch(
            self.git,
            Path(state["workspace"]),
            state["patch"],
            max_files=self.settings.max_patch_files,
            max_changed_lines=self.settings.max_patch_lines,
        )
        self.store.add_event(
            run_id,
            "info",
            "patch_validated",
            "补丁安全检查通过",
            {"files": summary.files, "changed_lines": summary.changed_lines},
        )
        return {}

    def _approve_patch(self, state: WorkflowState) -> dict[str, Any]:
        run_id = state["run_id"]
        self._status(run_id, RunStatus.AWAITING_PATCH_APPROVAL, "补丁等待人工审批")
        self.store.update_run(run_id, approval_stage=ApprovalStage.APPLY_PATCH)
        response = interrupt(
            {
                "stage": ApprovalStage.APPLY_PATCH.value,
                "run_id": run_id,
                "plan": state.get("repair_plan"),
                "patch": state["patch"],
                "attempt": state.get("attempt_count", 1),
            }
        )
        approved = bool(response.get("approved"))
        patch = response.get("edited_patch") or state["patch"]
        self.store.update_run(run_id, patch=patch, approval_stage=ApprovalStage.NONE)
        return {
            "approved": approved,
            "patch": patch,
            "rejected_stage": "apply_patch" if not approved else "",
        }

    def _apply(self, state: WorkflowState) -> dict[str, Any]:
        run_id = state["run_id"]
        self._status(run_id, RunStatus.APPLYING_PATCH, "正在应用已批准的补丁")
        workspace = Path(state["workspace"])
        validate_patch(
            self.git,
            workspace,
            state["patch"],
            max_files=self.settings.max_patch_files,
            max_changed_lines=self.settings.max_patch_lines,
        )
        self._ensure_active(run_id)
        self.git.apply_patch(workspace, state["patch"])
        self._ensure_active(run_id)
        complete_diff = self.git.diff(workspace)
        self.store.update_run(run_id, patch=complete_diff)
        self.store.add_event(run_id, "info", "patch_applied", "补丁已应用到隔离分支")
        return {"patch": complete_diff}

    def _test(self, state: WorkflowState) -> dict[str, Any]:
        run_id = state["run_id"]
        self._status(run_id, RunStatus.TESTING, "正在隔离容器中运行修复后测试")
        result = self.runner.run(
            Path(state["workspace"]),
            Language(state["language"]),
            state.get("test_command"),
            "post_patch",
        )
        self._ensure_active(run_id)
        self.store.update_run(
            run_id, test_result=result, patch=self.git.diff(Path(state["workspace"]))
        )
        self.store.add_event(
            run_id,
            "info" if result.passed else "warning",
            "test",
            "修复后测试通过" if result.passed else "修复后测试未通过",
            result.model_dump(),
        )
        return {"test_result": result.model_dump(), "approved": False}

    def _route_after_test(self, state: WorkflowState) -> Literal["retry", "push", "fail"]:
        result = TestResult.model_validate(state["test_result"])
        if result.passed:
            return "push"
        max_attempts = 1 + self.settings.max_repair_retries
        if not result.skipped_reason and int(state.get("attempt_count", 1)) < max_attempts:
            return "retry"
        return "fail"

    def _approve_push(self, state: WorkflowState) -> dict[str, Any]:
        run_id = state["run_id"]
        final_diff = self.git.diff(Path(state["workspace"]))
        self._status(run_id, RunStatus.AWAITING_PUSH_APPROVAL, "测试通过，等待最终提交与推送审批")
        self.store.update_run(
            run_id,
            patch=final_diff,
            approval_stage=ApprovalStage.PUSH_BRANCH,
        )
        response = interrupt(
            {
                "stage": ApprovalStage.PUSH_BRANCH.value,
                "run_id": run_id,
                "patch": final_diff,
                "branch": state["branch_name"],
                "tests": state["test_result"],
            }
        )
        approved = bool(response.get("approved"))
        self.store.update_run(run_id, approval_stage=ApprovalStage.NONE)
        if not approved:
            self.store.set_status(
                run_id, RunStatus.COMPLETED_LOCAL, "已保留本地修复分支，未推送远端"
            )
        return {"push_approved": approved, "rejected_stage": "push_branch" if not approved else ""}

    def _commit_push(self, state: WorkflowState) -> dict[str, Any]:
        run_id = state["run_id"]
        if not self.settings.github_token:
            raise RuntimeError("PATCHPILOT_GITHUB_TOKEN is required before final push approval")
        workspace = Path(state["workspace"])
        self._status(run_id, RunStatus.COMMITTING, "正在创建 Git 提交")
        self._ensure_active(run_id)
        commit_sha = self.git.commit(workspace, run_id)
        self.store.update_run(run_id, commit_sha=commit_sha)
        self._status(run_id, RunStatus.PUSHING, "正在推送新的 patchpilot 分支")
        self._ensure_active(run_id)
        remote_branch = self.git.push(workspace)
        self.store.update_run(run_id, remote_branch=remote_branch)
        self.store.set_status(run_id, RunStatus.COMPLETED, "修复分支已安全推送")
        self.store.add_event(
            run_id,
            "info",
            "completed",
            "PatchPilot 运行完成",
            {"commit_sha": commit_sha, "remote_branch": remote_branch},
        )
        return {"commit_sha": commit_sha, "remote_branch": remote_branch}

    def _reject(self, state: WorkflowState) -> dict[str, Any]:
        self.store.set_status(state["run_id"], RunStatus.REJECTED, "补丁被人工拒绝")
        return {}

    def _fail(self, state: WorkflowState) -> dict[str, Any]:
        result = TestResult.model_validate(state["test_result"])
        reason = result.skipped_reason or "修复在最大重试次数内仍未通过测试"
        self.store.update_run(state["run_id"], error=reason)
        self.store.set_status(state["run_id"], RunStatus.FAILED, reason)
        return {"error": reason}
