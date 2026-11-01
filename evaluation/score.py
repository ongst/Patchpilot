from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED_FIELDS = {
    "task_id",
    "approach",
    "patch_applied",
    "public_tests_passed",
    "hidden_tests_passed",
    "attempts",
    "tokens",
    "duration_seconds",
    "changed_file_count",
}

ALLOWED_APPROACHES = {"patchpilot", "single_prompt"}


def validate_records(records: list[dict]) -> None:
    seen: set[tuple[str, str]] = set()
    for index, record in enumerate(records):
        missing = REQUIRED_FIELDS - record.keys()
        if missing:
            raise ValueError(f"Record {index} is missing required fields: {sorted(missing)}")
        if record["approach"] not in ALLOWED_APPROACHES:
            raise ValueError(
                f"Record {index} has invalid approach {record['approach']!r}; "
                f"expected one of {sorted(ALLOWED_APPROACHES)}"
            )
        key = (record["task_id"], record["approach"])
        if key in seen:
            raise ValueError(
                f"Record {index} duplicates task {record['task_id']!r} "
                f"for approach {record['approach']!r}"
            )
        seen.add(key)


def _compute_metrics(records: list[dict]) -> dict[str, float | int]:
    total = len(records)
    return {
        "tasks": total,
        "patch_apply_rate": sum(bool(item["patch_applied"]) for item in records) / total,
        "hidden_test_pass_rate": sum(bool(item["hidden_tests_passed"]) for item in records) / total,
        "no_regression_rate": sum(bool(item["public_tests_passed"]) for item in records) / total,
        "average_tokens": round(sum(int(item["tokens"]) for item in records) / total),
        "average_duration_seconds": round(
            sum(float(item["duration_seconds"]) for item in records) / total, 2
        ),
        "average_changed_file_count": round(
            sum(int(item["changed_file_count"]) for item in records) / total, 2
        ),
    }


def score(path: Path) -> dict[str, dict[str, float | int]]:
    records = json.loads(path.read_text(encoding="utf-8"))
    if not records:
        raise ValueError("Evaluation results are empty")
    validate_records(records)
    grouped: dict[str, list[dict]] = {}
    for record in records:
        grouped.setdefault(record["approach"], []).append(record)
    return {approach: _compute_metrics(group) for approach, group in grouped.items()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    print(json.dumps(score(args.results), indent=2))
