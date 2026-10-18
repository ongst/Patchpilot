from datetime import UTC, datetime

from patchpilot.models import Language, RunRecord, RunStatus, TestResult
from patchpilot.reporting import build_run_report

PATCH = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
"""


def _run(status: RunStatus, **kwargs):
    return RunRecord(
        run_id="run-1", status=status,
        repo_url="https://github.com/owner/repo", issue_text="just a test issue",
        **kwargs,
    )


def test_report_completed_with_patch_and_tests():
    run = _run(
        RunStatus.COMPLETED,
        language=Language.PYTHON,
        patch=PATCH,
        attempt_count=1,
        token_usage=2840,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        finished_at=datetime(2026, 1, 1, 0, 0, 30, tzinfo=UTC),
        baseline_result=TestResult(command="pytest", passed=False),
        test_result=TestResult(command="pytest", passed=True),
    )
    report = build_run_report(run)
    assert report.status == RunStatus.COMPLETED
    assert report.additions == 1
    assert report.deletions == 1
    assert len(report.changed_files) == 1
    assert report.attempt_count == 1
    assert report.token_usage == 2840
    assert report.duration_seconds == 30.0
    assert report.baseline_result.passed is False
    assert report.test_result.passed is True


def test_report_failed_keeps_error():
    run = _run(RunStatus.FAILED, error="something went wrong")
    report = build_run_report(run)
    assert report.status == RunStatus.FAILED
    assert report.error == "something went wrong"
    assert report.changed_files == []
    assert report.additions == 0


def test_report_cancelled_is_not_failed():
    run = _run(RunStatus.CANCELLED)
    report = build_run_report(run)
    assert report.status == RunStatus.CANCELLED


def test_report_duration_floor_and_fallback():
    run = _run(
        RunStatus.COMPLETED,
        started_at=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
        finished_at=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    )
    assert build_run_report(run).duration_seconds == 0.0

    run2 = _run(RunStatus.COMPLETED)
    assert build_run_report(run2).duration_seconds >= 0.0
