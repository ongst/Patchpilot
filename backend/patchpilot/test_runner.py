from __future__ import annotations

import shutil
import subprocess
import time
import uuid
from pathlib import Path

from patchpilot.config import Settings
from patchpilot.models import Language, TestResult
from patchpilot.security import (
    SecurityError,
    ValidatedCommand,
    redact_secrets,
    validate_test_command,
)


class DockerTestRunner:
    def __init__(self, settings: Settings):
        self.settings = settings

    def available(self) -> bool:
        if not self.settings.docker_enabled or shutil.which("docker") is None:
            return False
        try:
            result = subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"],
                capture_output=True,
                text=True,
                timeout=10,
                shell=False,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def detect_command(
        self, repo: Path, language: Language, requested: str | None
    ) -> ValidatedCommand:
        if requested:
            return validate_test_command(requested, language.value)
        if language == Language.PYTHON:
            return ValidatedCommand(["python", "-m", "pytest", "-q"], "python -m pytest -q")
        if language == Language.JAVASCRIPT:
            if not (repo / "package-lock.json").exists():
                raise SecurityError("JavaScript repositories require package-lock.json in v1")
            return ValidatedCommand(["npm", "test"], "npm test")
        raise SecurityError("Unable to detect a supported test command")

    def run(
        self,
        repo: Path,
        language: Language,
        requested_command: str | None,
        phase: str,
    ) -> TestResult:
        command = self.detect_command(repo, language, requested_command)
        if not self.available():
            return TestResult(
                command=command.display,
                passed=False,
                phase=phase,
                skipped_reason="Docker daemon is not available",
            )

        volume = f"patchpilot-deps-{uuid.uuid4().hex[:12]}"
        started = time.monotonic()
        try:
            setup = self._setup_dependencies(repo, language, volume)
            if setup.returncode != 0:
                return TestResult(
                    command=command.display,
                    exit_code=setup.returncode,
                    passed=False,
                    output=self._clip(setup.stdout + setup.stderr),
                    duration_seconds=time.monotonic() - started,
                    phase=phase,
                )
            result = self._execute_tests(repo, language, volume, command.argv)
            return TestResult(
                command=command.display,
                exit_code=result.returncode,
                passed=result.returncode == 0,
                output=self._clip(result.stdout + result.stderr),
                duration_seconds=time.monotonic() - started,
                phase=phase,
            )
        except subprocess.TimeoutExpired as error:
            output = (error.stdout or "") + (error.stderr or "")
            return TestResult(
                command=command.display,
                exit_code=None,
                passed=False,
                output=self._clip(str(output)),
                duration_seconds=time.monotonic() - started,
                phase=phase,
                skipped_reason="Test execution timed out",
            )
        finally:
            subprocess.run(
                ["docker", "volume", "rm", "-f", volume],
                capture_output=True,
                text=True,
                timeout=30,
                shell=False,
            )

    def _limits(self) -> list[str]:
        return [
            "--cpus",
            str(self.settings.docker_cpus),
            "--memory",
            self.settings.docker_memory,
            "--pids-limit",
            str(self.settings.docker_pids_limit),
        ]

    def _setup_dependencies(self, repo: Path, language: Language, volume: str):
        mount = f"{repo.resolve()}:/workspace:ro"
        if language == Language.PYTHON:
            script = (
                "python -m pip install --disable-pip-version-check --no-cache-dir --target /deps pytest && "
                "if [ -f /workspace/requirements.txt ]; then "
                "python -m pip install --disable-pip-version-check --no-cache-dir --target /deps -r /workspace/requirements.txt; "
                "elif [ -f /workspace/pyproject.toml ]; then "
                "python -m pip install --disable-pip-version-check --no-cache-dir --target /deps /workspace; fi"
            )
            args = [
                "docker",
                "run",
                "--rm",
                *self._limits(),
                "--network",
                "bridge",
                "-v",
                mount,
                "-v",
                f"{volume}:/deps",
                "python:3.12-slim",
                "sh",
                "-lc",
                script,
            ]
        else:
            args = [
                "docker",
                "run",
                "--rm",
                *self._limits(),
                "--network",
                "bridge",
                "-v",
                mount,
                "-v",
                f"{volume}:/workspace/node_modules",
                "-w",
                "/workspace",
                "node:22-bookworm-slim",
                "npm",
                "ci",
                "--ignore-scripts",
                "--no-audit",
                "--no-fund",
            ]
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=self.settings.test_timeout_seconds,
            shell=False,
        )

    def _execute_tests(self, repo: Path, language: Language, volume: str, command: list[str]):
        mount = f"{repo.resolve()}:/workspace:ro"
        image = "python:3.12-slim" if language == Language.PYTHON else "node:22-bookworm-slim"
        dependency_mount = (
            f"{volume}:/deps:ro"
            if language == Language.PYTHON
            else f"{volume}:/workspace/node_modules:ro"
        )
        args = [
            "docker",
            "run",
            "--rm",
            *self._limits(),
            "--network",
            "none",
            "--user",
            "65534:65534",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=128m",
            "-v",
            mount,
            "-v",
            dependency_mount,
            "-w",
            "/workspace",
        ]
        if language == Language.PYTHON:
            args.extend(["-e", "PYTHONPATH=/deps:/workspace", "-e", "PYTHONDONTWRITEBYTECODE=1"])
        args.extend([image, *command])
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=self.settings.test_timeout_seconds,
            shell=False,
        )

    def _clip(self, output: str) -> str:
        clean = redact_secrets(output, [self.settings.llm_api_key, self.settings.github_token])
        limit = self.settings.max_tool_output_chars
        return clean if len(clean) <= limit else clean[-limit:] + "\n... output truncated"
