from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from patchpilot.git_service import GitService
from patchpilot.security import SecurityError, is_ignored, safe_repo_path

DIFF_PATH = re.compile(r"^diff --git a/(.+) b/(.+)$")


@dataclass(frozen=True)
class PatchSummary:
    files: list[str]
    changed_lines: int


def validate_patch_structure(
    repo: Path,
    patch: str,
    *,
    max_files: int = 8,
    max_changed_lines: int = 800,
) -> PatchSummary:
    if not patch.strip() or "diff --git " not in patch:
        raise SecurityError("A unified git diff is required")
    files: list[str] = []
    changed_lines = 0
    for line in patch.splitlines():
        match = DIFF_PATH.match(line)
        if match:
            left, right = match.groups()
            if left != right and left != "/dev/null" and right != "/dev/null":
                raise SecurityError("Renames are not supported in the first version")
            candidate = right if right != "/dev/null" else left
            path = PurePosixPath(candidate)
            if path.is_absolute() or ".." in path.parts or is_ignored(path):
                raise SecurityError(f"Patch contains an unsafe path: {candidate}")
            safe_repo_path(repo, candidate, must_exist=False)
            files.append(candidate)
        elif (line.startswith("+") and not line.startswith("+++")) or (
            line.startswith("-") and not line.startswith("---")
        ):
            changed_lines += 1

    unique_files = list(dict.fromkeys(files))
    if not unique_files:
        raise SecurityError("Patch does not contain any file changes")
    if len(unique_files) > max_files:
        raise SecurityError(f"Patch changes {len(unique_files)} files; limit is {max_files}")
    if changed_lines > max_changed_lines:
        raise SecurityError(f"Patch changes {changed_lines} lines; limit is {max_changed_lines}")
    return PatchSummary(files=unique_files, changed_lines=changed_lines)


def validate_patch(
    git: GitService,
    repo: Path,
    patch: str,
    *,
    max_files: int,
    max_changed_lines: int,
) -> PatchSummary:
    summary = validate_patch_structure(
        repo,
        patch,
        max_files=max_files,
        max_changed_lines=max_changed_lines,
    )
    git.apply_check(repo, patch)
    return summary
