from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from patchpilot.git_service import GitService
from patchpilot.security import SecurityError


def _init_repo(path: Path, branch: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", branch], cwd=path, check=True, capture_output=True)
    (path / "file.txt").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "file.txt"], cwd=path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=t@e.com", "commit", "-m", "init"],
        cwd=path, check=True, capture_output=True,
    )


def test_commit_rejected_on_default_branch(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo, "main")
    git = GitService()
    with pytest.raises(SecurityError):
        git.commit(repo, "12345678")


def test_push_rejected_on_default_branch(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo, "main")
    git = GitService()
    with pytest.raises(SecurityError):
        git.push(repo)


def test_push_requires_token(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo, "patchpilot/run-1234abcd")
    git = GitService(github_token="")
    with pytest.raises(SecurityError, match="PATCHPILOT_GITHUB_TOKEN"):
        git.push(repo)


def test_token_not_in_command_args(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    _init_repo(repo, "patchpilot/run-1234abcd")
    fake_token = "github_pat_fake123456789"
    git = GitService(github_token=fake_token)

    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = list(args)
        captured["env"] = dict(kwargs.get("env", {}))
        stdout = "patchpilot/run-1234abcd\n" if "--show-current" in args else ""
        return subprocess.CompletedProcess(list(args), 0, stdout=stdout, stderr="")

    monkeypatch.setattr("patchpilot.git_service.subprocess.run", fake_run)

    git.push(repo)

    assert fake_token not in " ".join(captured["args"])
    header = captured["env"]["GIT_CONFIG_VALUE_0"]
    assert header.startswith("AUTHORIZATION: basic ")
    assert fake_token not in header


def test_token_redacted_from_error(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    _init_repo(repo, "patchpilot/run-1234abcd")
    fake_token = "github_pat_fake123456789"
    git = GitService(github_token=fake_token)

    def fake_run(args, **kwargs):
        if "--show-current" in args:
            return subprocess.CompletedProcess(
                list(args), 0, stdout="patchpilot/run-1234abcd\n", stderr=""
            )
        return subprocess.CompletedProcess(
            list(args), 1, stdout="", stderr=f"fatal: {fake_token} invalid"
        )

    monkeypatch.setattr("patchpilot.git_service.subprocess.run", fake_run)

    with pytest.raises(RuntimeError) as excinfo:
        git.push(repo)

    assert fake_token not in str(excinfo.value)
    assert "***REDACTED***" in str(excinfo.value)


def test_push_has_no_force_flags(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    _init_repo(repo, "patchpilot/run-1234abcd")
    git = GitService(github_token="github_pat_fake")

    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = list(args)
        stdout = "patchpilot/run-1234abcd\n" if "--show-current" in args else ""
        return subprocess.CompletedProcess(list(args), 0, stdout=stdout, stderr="")

    monkeypatch.setattr("patchpilot.git_service.subprocess.run", fake_run)

    git.push(repo)

    for flag in ("--force", "--force-with-lease", "-f"):
        assert flag not in captured["args"]
