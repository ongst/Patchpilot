from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class RunStatus(StrEnum):
    QUEUED = "queued"
    CLONING = "cloning"
    PROFILING = "profiling"
    BASELINE_TESTING = "baseline_testing"
    PLANNING = "planning"
    VALIDATING_PATCH = "validating_patch"
    AWAITING_PATCH_APPROVAL = "awaiting_patch_approval"
    APPLYING_PATCH = "applying_patch"
    TESTING = "testing"
    REPAIRING = "repairing"
    AWAITING_PUSH_APPROVAL = "awaiting_push_approval"
    COMMITTING = "committing"
    PUSHING = "pushing"
    COMPLETED = "completed"
    COMPLETED_LOCAL = "completed_local"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    FAILED = "failed"

    @property
    def terminal(self) -> bool:
        return self in {
            self.COMPLETED,
            self.COMPLETED_LOCAL,
            self.REJECTED,
            self.CANCELLED,
            self.FAILED,
        }


class Language(StrEnum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    UNKNOWN = "unknown"


class ApprovalStage(StrEnum):
    NONE = "none"
    APPLY_PATCH = "apply_patch"
    PUSH_BRANCH = "push_branch"


class RepairPlan(BaseModel):
    summary: str
    root_cause: str
    steps: list[str] = Field(min_length=1)
    tests: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class TestResult(BaseModel):
    command: str
    exit_code: int | None = None
    passed: bool = False
    output: str = ""
    duration_seconds: float = 0.0
    phase: Literal["baseline", "post_patch"] = "post_patch"
    skipped_reason: str | None = None


class RunCreate(BaseModel):
    repo_url: HttpUrl
    issue_text: str = Field(min_length=10, max_length=20_000)
    test_command: str | None = Field(default=None, max_length=300)

    @field_validator("repo_url")
    @classmethod
    def github_https_only(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https" or value.host not in {"github.com", "www.github.com"}:
            raise ValueError("Only public HTTPS GitHub repository URLs are supported")
        return value


class DecisionRequest(BaseModel):
    stage: ApprovalStage
    decision: Literal["approve", "reject"]
    edited_patch: str | None = None


class RunRecord(BaseModel):
    run_id: str
    status: RunStatus
    repo_url: str
    issue_text: str
    test_command: str | None = None
    language: Language = Language.UNKNOWN
    branch_name: str = ""
    workspace: str = ""
    repair_plan: RepairPlan | None = None
    inspected_files: list[str] = Field(default_factory=list)
    patch: str = ""
    attempt_count: int = 0
    baseline_result: TestResult | None = None
    test_result: TestResult | None = None
    approval_stage: ApprovalStage = ApprovalStage.NONE
    commit_sha: str = ""
    remote_branch: str = ""
    token_usage: int = 0
    error: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RunReport(BaseModel):
    run_id: str
    status: RunStatus
    repo_url: str
    issue_text: str
    language: Language
    branch_name: str

    plan_summary: str = ""
    inspected_file_count: int = 0
    changed_files: list[DiffFileSummary] = []
    additions: int = 0
    deletions: int = 0

    attempt_count: int = 0
    baseline_result: TestResult | None = None
    test_result: TestResult | None = None

    token_usage: int = 0
    duration_seconds: float = 0.0

    commit_sha: str = ""
    remote_branch: str = ""
    error: str = ""


class RunEvent(BaseModel):
    id: int
    run_id: str
    level: Literal["info", "warning", "error"]
    event_type: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: bool
    git: bool
    docker: bool
    llm_configured: bool
    version: str
    ready_for_repair: bool
    ready_for_push: bool


class DiffFileSummary(BaseModel):
    path: str
    additions: int = 0
    deletions: int = 0


class DiffResponse(BaseModel):
    run_id: str
    patch: str
    files: list[DiffFileSummary]
    additions: int
    deletions: int
    changed_lines: int
