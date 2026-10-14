from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from langgraph.types import Command

from patchpilot.config import Settings
from patchpilot.db import RunStore
from patchpilot.models import ApprovalStage, DecisionRequest, RunCreate, RunRecord, RunStatus
from patchpilot.security import validate_repo_url
from patchpilot.workflow import RunCancelledError, WorkflowEngine


class RunService:
    def __init__(self, settings: Settings, store: RunStore, workflow: WorkflowEngine):
        self.settings = settings
        self.store = store
        self.workflow = workflow
        self._active: set[str] = set()
        self._lock = threading.Lock()

    def create(self, request: RunCreate) -> RunRecord:
        run_id = uuid.uuid4().hex
        run = RunRecord(
            run_id=run_id,
            status=RunStatus.QUEUED,
            repo_url=validate_repo_url(str(request.repo_url)),
            issue_text=request.issue_text,
            test_command=request.test_command,
        )
        self.store.create_run(run)
        self.store.add_event(run_id, "info", "created", "PatchPilot 运行已创建")
        self._launch(run_id, self._initial_state(run))
        return run

    def decide(self, run_id: str, request: DecisionRequest) -> RunRecord:
        run = self._require(run_id)
        if run.approval_stage != request.stage or request.stage == ApprovalStage.NONE:
            raise ValueError(f"Run is not waiting for {request.stage.value} approval")
        payload: dict[str, Any] = {"approved": request.decision == "approve"}
        if request.stage == ApprovalStage.APPLY_PATCH and request.edited_patch:
            payload["edited_patch"] = request.edited_patch
        self.store.add_event(
            run_id,
            "info",
            "decision",
            f"用户已{('批准' if payload['approved'] else '拒绝')} {request.stage.value}",
        )
        self._launch(run_id, Command(resume=payload))
        return self._require(run_id)

    def cancel(self, run_id: str) -> RunRecord:
        run = self._require(run_id)
        if run.status.terminal:
            return run
        return self.store.set_status(run_id, RunStatus.CANCELLED, "运行已由用户取消")

    def _initial_state(self, run: RunRecord) -> dict[str, Any]:
        return {
            "run_id": run.run_id,
            "repo_url": run.repo_url,
            "issue_text": run.issue_text,
            "test_command": run.test_command,
            "attempt_count": 0,
            "token_usage": 0,
        }

    def _launch(self, run_id: str, graph_input: Any) -> None:
        with self._lock:
            if run_id in self._active:
                raise ValueError("Run is already executing")
            self._active.add(run_id)

        def worker() -> None:
            try:
                self.workflow.graph.invoke(graph_input, config=self.workflow.config_for(run_id))
            except RunCancelledError:
                pass
            except Exception as error:
                run = self.store.get_run(run_id)
                if run and run.status != RunStatus.CANCELLED:
                    self.store.update_run(run_id, error=str(error), finished_at=datetime.now(UTC))
                    self.store.set_status(run_id, RunStatus.FAILED, "运行失败")
                    self.store.add_event(run_id, "error", "exception", str(error))
            finally:
                with self._lock:
                    self._active.discard(run_id)

        threading.Thread(target=worker, name=f"patchpilot-{run_id[:8]}", daemon=True).start()

    def _require(self, run_id: str) -> RunRecord:
        run = self.store.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        return run
