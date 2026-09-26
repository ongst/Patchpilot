from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from patchpilot.security import SecurityError, redact_secrets, validate_repo_url


@dataclass(frozen=True)
class GitResult:
    stdout: str
    stderr: str
    returncode: int


class GitService:
    def __init__(
        self,
        github_token: str = "",
        author_name: str = "PatchPilot Agent",
        author_email: str = "patchpilot@localhost",
    ):
        self.github_token = github_token
        self.author_name = author_name
        self.author_email = author_email

    def _run(
        self,
        args: list[str],
        cwd: Path | None = None,
        *,
        check: bool = True,
        authenticated: bool = False,
        input_text: str | None = None,
    ) -> GitResult:
        environment = os.environ.copy()
        environment["GIT_TERMINAL_PROMPT"] = "0"
        if authenticated:
            if not self.github_token:
                raise SecurityError("PATCHPILOT_GITHUB_TOKEN is required to push")
            environment.update(
                {
                    "GIT_CONFIG_COUNT": "1",
                    "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
                    "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: bearer {self.github_token}",
                }
            )
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=environment,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=180,
            shell=False,
        )
        stdout = redact_secrets(completed.stdout, [self.github_token])
        stderr = redact_secrets(completed.stderr, [self.github_token])
        result = GitResult(stdout=stdout, stderr=stderr, returncode=completed.returncode)
        if check and completed.returncode != 0:
            raise RuntimeError(f"git {' '.join(args[:2])} failed: {stderr or stdout}")
        return result

    def clone_and_branch(self, repo_url: str, destination: Path, run_id: str) -> str:
        validate_repo_url(repo_url)
        if destination.exists():
            raise SecurityError("Run workspace already exists")
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._run(["clone", "--depth", "1", "--", repo_url, str(destination)])
        branch = f"patchpilot/run-{run_id[:8]}"
        self._run(["switch", "-c", branch], cwd=destination)
        return branch

    def current_branch(self, repo: Path) -> str:
        return self._run(["branch", "--show-current"], cwd=repo).stdout.strip()

    def ensure_patchpilot_branch(self, repo: Path) -> str:
        branch = self.current_branch(repo)
        if not re.fullmatch(r"patchpilot/run-[a-f0-9]{8}", branch):
            raise SecurityError("Git writes are restricted to patchpilot/run-* branches")
        return branch

    def diff(self, repo: Path) -> str:
        return self._run(["diff", "--binary", "--no-ext-diff"], cwd=repo).stdout

    def status(self, repo: Path) -> str:
        return self._run(["status", "--short"], cwd=repo).stdout

    def apply_check(self, repo: Path, patch: str) -> None:
        self.ensure_patchpilot_branch(repo)
        self._run(
            ["apply", "--check", "--whitespace=error-all", "-"],
            cwd=repo,
            input_text=patch,
        )

    def apply_patch(self, repo: Path, patch: str) -> None:
        self.apply_check(repo, patch)
        self._run(["apply", "--whitespace=fix", "-"], cwd=repo, input_text=patch)

    def commit(self, repo: Path, run_id: str) -> str:
        self.ensure_patchpilot_branch(repo)
        self._run(["add", "-A"], cwd=repo)
        if not self.status(repo):
            raise RuntimeError("No changes are available to commit")
        self._run(
            [
                "-c",
                f"user.name={self.author_name}",
                "-c",
                f"user.email={self.author_email}",
                "commit",
                "-m",
                f"fix: PatchPilot repair {run_id[:8]}",
            ],
            cwd=repo,
        )
        return self._run(["rev-parse", "HEAD"], cwd=repo).stdout.strip()

    def push(self, repo: Path) -> str:
        branch = self.ensure_patchpilot_branch(repo)
        self._run(["push", "--set-upstream", "origin", branch], cwd=repo, authenticated=True)
        return branch
