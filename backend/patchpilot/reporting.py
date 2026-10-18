from __future__ import annotations

from patchpilot.models import RunRecord, RunReport
from patchpilot.patching import parse_patch_summary


def build_run_report(run: RunRecord) -> RunReport:
    files = parse_patch_summary(run.patch)
    started = run.started_at or run.created_at
    finished = run.finished_at or run.updated_at
    duration = max(0.0, (finished - started).total_seconds())
    return RunReport(
        run_id=run.run_id,
        status=run.status,
        repo_url=run.repo_url,
        issue_text=run.issue_text,
        language=run.language,
        branch_name=run.branch_name,
        plan_summary=run.repair_plan.summary if run.repair_plan else "",
        inspected_file_count=len(run.inspected_files),
        changed_files=files,
        additions=sum(f.additions for f in files),
        deletions=sum(f.deletions for f in files),
        attempt_count=run.attempt_count,
        baseline_result=run.baseline_result,
        test_result=run.test_result,
        token_usage=run.token_usage,
        duration_seconds=duration,
        commit_sha=run.commit_sha,
        remote_branch=run.remote_branch,
        error=run.error,
    )
