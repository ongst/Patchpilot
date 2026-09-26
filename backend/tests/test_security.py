from pathlib import Path

import pytest
from patchpilot.security import (
    SecurityError,
    redact_secrets,
    safe_repo_path,
    validate_repo_url,
    validate_test_command,
)


def test_repo_url_accepts_only_public_github_https():
    assert validate_repo_url("https://github.com/openai/openai-python")
    with pytest.raises(SecurityError):
        validate_repo_url("http://github.com/openai/openai-python")
    with pytest.raises(SecurityError):
        validate_repo_url("https://example.com/a/b")
    with pytest.raises(SecurityError):
        validate_repo_url("https://github.com/a/b/issues/1")


def test_safe_repo_path_rejects_escape_and_ignored_paths(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')", encoding="utf-8")
    assert safe_repo_path(tmp_path, "src/app.py") == (tmp_path / "src" / "app.py").resolve()
    with pytest.raises(SecurityError):
        safe_repo_path(tmp_path, "../secret.txt", must_exist=False)
    with pytest.raises(SecurityError):
        safe_repo_path(tmp_path, ".git/config", must_exist=False)


@pytest.mark.parametrize(
    ("language", "command"),
    [
        ("python", "pytest -q"),
        ("python", "python -m pytest tests/test_api.py"),
        ("javascript", "npm test"),
        ("javascript", "npm run lint"),
        ("javascript", "npm run typecheck"),
    ],
)
def test_test_command_allowlist(language: str, command: str):
    assert validate_test_command(command, language).argv


@pytest.mark.parametrize(
    "command",
    ["pytest; whoami", "npm test && curl bad", "bash -c pytest", "python setup.py test"],
)
def test_test_command_rejects_shell_and_unapproved_commands(command: str):
    with pytest.raises(SecurityError):
        validate_test_command(command, "python")


def test_secret_redaction():
    value = redact_secrets("Authorization: bearer token123 api_key=abc", ["token123"])
    assert "token123" not in value
    assert "abc" not in value
