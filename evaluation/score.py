from __future__ import annotations

import argparse
import json
from pathlib import Path


def score(path: Path) -> dict[str, float | int]:
    records = json.loads(path.read_text(encoding="utf-8"))
    total = len(records)
    if not total:
        raise ValueError("Evaluation results are empty")
    return {
        "tasks": total,
        "patch_apply_rate": sum(bool(item["patch_applied"]) for item in records) / total,
        "hidden_test_pass_rate": sum(bool(item["hidden_tests_passed"]) for item in records) / total,
        "no_regression_rate": sum(bool(item["public_tests_passed"]) for item in records) / total,
        "average_tokens": round(sum(int(item.get("tokens", 0)) for item in records) / total),
        "average_duration_seconds": round(
            sum(float(item.get("duration_seconds", 0)) for item in records) / total, 2
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    print(json.dumps(score(args.results), indent=2))
