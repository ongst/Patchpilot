"""Single-prompt baseline executor for the PatchPilot evaluation.

Unlike the PatchPilot workflow — which inspects the repository through tools
over multiple rounds — this baseline sends the model one prompt containing the
issue and the full repository files, then asks for a single unified diff. The
returned patch is applied and scored with the same Docker test runner and the
same hidden tests as the PatchPilot approach, so the two are comparable.

Run from the repository root:

    python evaluation/single_prompt.py --task py-clamp
    python evaluation/single_prompt.py --output evaluation/results/single_prompt.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from openai import OpenAI
from patchpilot.config import Settings, get_settings
from patchpilot.models import Language
from patchpilot.test_runner import DockerTestRunner

from tasks import TASKS

SYSTEM_PROMPT = """You are a code repair assistant.
You are given the full contents of a small repository and a bug report.
Return exactly one JSON object with the key:
{"patch": "a complete unified git diff beginning with diff --git"}
The patch must fix the reported bug and be minimal. Do not wrap the JSON in
Markdown fences. Do not execute commands or invent files that are not shown.
"""


def read_files(files: dict[str, str]) -> str:
    return "\n\n".join(f"### {path}\n{content}" for path, content in sorted(files.items()))


def extract_json(content: str) -> dict:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def generate_patch(settings: Settings, task) -> tuple[str, int]:
    if not settings.llm_api_key:
        raise RuntimeError("PATCHPILOT_LLM_API_KEY is not configured")
    client = OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout_seconds,
    )
    user_prompt = (
        f"Repository language: {task.language}\n"
        f"Bug report:\n{task.issue}\n\n"
        f"Repository files:\n{read_files(task.files)}"
    )
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
    )
    tokens = response.usage.total_tokens if response.usage else 0
    content = response.choices[0].message.content or ""
    patch = extract_json(content).get("patch", "")
    if not patch or "diff --git " not in patch:
        raise ValueError("Model did not return a valid unified diff")
    return patch, tokens


def init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=eval",
            "-c",
            "user.email=eval@localhost",
            "commit",
            "-m",
            "initial",
        ],
        cwd=path,
        check=True,
        capture_output=True,
    )


def apply_patch(path: Path, patch: str) -> bool:
    normalized = patch.replace("\r\n", "\n")
    check = subprocess.run(
        ["git", "apply", "--check", "--whitespace=warn", "-"],
        cwd=path,
        input=normalized,
        text=True,
        capture_output=True,
    )
    if check.returncode != 0:
        return False
    applied = subprocess.run(
        ["git", "apply", "--whitespace=fix", "-"],
        cwd=path,
        input=normalized,
        text=True,
        capture_output=True,
    )
    return applied.returncode == 0


def count_files(patch: str) -> int:
    return sum(1 for line in patch.splitlines() if line.startswith("diff --git "))


def run_task(task, settings: Settings, runner: DockerTestRunner) -> dict:
    started = time.monotonic()
    language = Language(task.language)
    tokens = 0
    patch_applied = False
    patch = ""

    with tempfile.TemporaryDirectory() as directory:
        repo = Path(directory) / "repo"
        repo.mkdir()
        for relative, content in task.files.items():
            target = repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        init_repo(repo)

        try:
            patch, tokens = generate_patch(settings, task)
            patch_applied = apply_patch(repo, patch)
        except Exception as error:
            print(f"  patch generation failed: {type(error).__name__}: {error}", flush=True)

        public = runner.run(repo, language, task.test_command, "post_patch")

        # Isolate the hidden test: remove any test files the model added, so the
        # hidden score reflects only the ground-truth test, not the model's own.
        for directory in {Path(relative).parent for relative in task.hidden_tests}:
            target = repo / directory
            if target.exists():
                shutil.rmtree(target)
        for path in list(repo.rglob("*")):
            if path.is_file() and (
                path.name.endswith(".test.js")
                or path.name.startswith("test_")
                or path.name.endswith("_test.py")
            ):
                path.unlink()

        for relative, content in task.hidden_tests.items():
            target = repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        hidden = runner.run(repo, language, task.test_command, "post_patch")

    return {
        "task_id": task.task_id,
        "approach": "single_prompt",
        "patch_applied": patch_applied,
        "public_tests_passed": bool(public.passed),
        "hidden_tests_passed": bool(hidden.passed),
        "attempts": 1,
        "tokens": tokens,
        "duration_seconds": round(time.monotonic() - started, 2),
        "changed_file_count": count_files(patch) if patch_applied else 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", action="append", default=[], help="task_id to run (repeatable)")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/results/single_prompt.json"),
        help="JSON output path",
    )
    args = parser.parse_args()

    settings = get_settings()
    runner = DockerTestRunner(settings)
    selected = [task for task in TASKS if not args.task or task.task_id in args.task]

    records = []
    for task in selected:
        print(f"[{task.task_id}] running single_prompt baseline ...", flush=True)
        try:
            records.append(run_task(task, settings, runner))
        except Exception as error:
            print(f"[{task.task_id}] ERROR {type(error).__name__}: {error}", flush=True)
            records.append(
                {
                    "task_id": task.task_id,
                    "approach": "single_prompt",
                    "patch_applied": False,
                    "public_tests_passed": False,
                    "hidden_tests_passed": False,
                    "attempts": 1,
                    "tokens": 0,
                    "duration_seconds": 0.0,
                    "changed_file_count": 0,
                    "error": f"{type(error).__name__}: {error}",
                }
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"WROTE {args.output}", flush=True)


if __name__ == "__main__":
    main()
