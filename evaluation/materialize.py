from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from tasks import TASKS


def materialize(destination: Path, include_hidden: bool = False) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    manifest = []
    for task in TASKS:
        root = destination / task.task_id
        if root.exists():
            shutil.rmtree(root)
        for relative, content in task.files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        if include_hidden:
            for relative, content in task.hidden_tests.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
        manifest.append(
            {
                "task_id": task.task_id,
                "language": task.language,
                "issue": task.issue,
                "test_command": task.test_command,
            }
        )
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument("--include-hidden", action="store_true")
    args = parser.parse_args()
    materialize(args.destination, args.include_hidden)
