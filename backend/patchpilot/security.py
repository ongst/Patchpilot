from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

IGNORED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".next",
    ".pytest_cache",
    "__pycache__",
    ".patchpilot",
}

BINARY_SUFFIXES = {
    ".7z",
    ".bin",
    ".class",
    ".dll",
    ".dylib",
    ".exe",
    ".gif",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".lockb",
    ".pdf",
    ".png",
    ".pyc",
    ".so",
    ".tar",
    ".webp",
    ".woff",
    ".woff2",
    ".zip",
}

GITHUB_REPO_PATTERN = re.compile(
    r"^https://(?:www\.)?github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?/?$"
)


class SecurityError(ValueError):
    pass


def validate_repo_url(repo_url: str) -> str:
    if not GITHUB_REPO_PATTERN.fullmatch(repo_url):
        raise SecurityError("Only public HTTPS GitHub repository URLs are supported")
    return repo_url.rstrip("/")


def is_ignored(relative_path: str | Path) -> bool:
    path = PurePosixPath(str(relative_path).replace("\\", "/"))
    return (
        any(part in IGNORED_PARTS for part in path.parts) or path.suffix.lower() in BINARY_SUFFIXES
    )


def safe_repo_path(root: Path, relative_path: str, *, must_exist: bool = True) -> Path:
    candidate_input = Path(relative_path)
    if candidate_input.is_absolute():
        raise SecurityError("Absolute paths are not allowed")
    normalized = PurePosixPath(relative_path.replace("\\", "/"))
    if ".." in normalized.parts or is_ignored(normalized):
        raise SecurityError("Path escapes or ignored paths are not allowed")

    root_resolved = root.resolve()
    candidate = (root / Path(*normalized.parts)).resolve(strict=False)
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise SecurityError("Path escapes repository workspace")
    if must_exist and not candidate.exists():
        raise SecurityError(f"Path does not exist: {relative_path}")
    if candidate.exists() and candidate.is_symlink():
        target = candidate.resolve()
        if root_resolved not in target.parents:
            raise SecurityError("Symlink escapes repository workspace")
    return candidate


@dataclass(frozen=True)
class ValidatedCommand:
    argv: list[str]
    display: str


def validate_test_command(command: str, language: str) -> ValidatedCommand:
    if any(marker in command for marker in (";", "&&", "||", "|", ">", "<", "`", "$", "\n")):
        raise SecurityError("Shell operators are not allowed in test commands")
    try:
        argv = shlex.split(command, posix=True)
    except ValueError as error:
        raise SecurityError("Invalid test command") from error
    if not argv:
        raise SecurityError("Test command cannot be empty")

    allowed = False
    if language == "python":
        allowed = argv[0] == "pytest" or argv[:3] == ["python", "-m", "pytest"]
    elif language == "javascript":
        allowed = (
            argv[:2] == ["npm", "test"]
            or argv[:2] == ["npm", "run"]
            and len(argv) >= 3
            and argv[2]
            in {
                "test",
                "lint",
                "typecheck",
            }
        )
    if not allowed:
        raise SecurityError("Test command is outside the allowed command set")
    return ValidatedCommand(argv=argv, display=" ".join(argv))


def redact_secrets(text: str, secrets: list[str]) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "***REDACTED***")
    redacted = re.sub(r"(?i)(authorization:\s*(?:bearer|token)\s+)[^\s]+", r"\1***", redacted)
    redacted = re.sub(r"(?i)(api[_-]?key[=:]\s*)[^\s]+", r"\1***", redacted)
    return redacted
