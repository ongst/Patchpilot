import json

import pytest

from evaluation.score import score, validate_records


def _record(task_id: str, approach: str, *, passed: bool) -> dict:
    return {
        "task_id": task_id,
        "approach": approach,
        "patch_applied": passed,
        "public_tests_passed": True,
        "hidden_tests_passed": passed,
        "attempts": 1,
        "tokens": 100,
        "duration_seconds": 2.5,
        "changed_file_count": 1,
    }


def test_score_groups_results_by_approach(tmp_path):
    path = tmp_path / "results.json"
    path.write_text(
        json.dumps(
            [
                _record("task-a", "patchpilot", passed=False),
                _record("task-a", "single_prompt", passed=True),
            ]
        ),
        encoding="utf-8",
    )

    result = score(path)

    assert result["patchpilot"]["tasks"] == 1
    assert result["patchpilot"]["hidden_test_pass_rate"] == 0
    assert result["single_prompt"]["tasks"] == 1
    assert result["single_prompt"]["hidden_test_pass_rate"] == 1


def test_validate_records_rejects_duplicate_task_and_approach():
    record = _record("task-a", "patchpilot", passed=True)

    with pytest.raises(ValueError, match="duplicates task"):
        validate_records([record, record.copy()])


def test_validate_records_allows_same_task_for_different_approaches():
    validate_records(
        [
            _record("task-a", "patchpilot", passed=True),
            _record("task-a", "single_prompt", passed=True),
        ]
    )
