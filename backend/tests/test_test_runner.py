from pathlib import Path

import pytest
from patchpilot.config import Settings
from patchpilot.models import Language
from patchpilot.security import SecurityError
from patchpilot.test_runner import DockerTestRunner


def test_detect_commands_and_missing_lockfile(tmp_path: Path):
    runner = DockerTestRunner(Settings(data_dir=tmp_path / "data", workspace_dir=tmp_path / "work"))
    assert runner.detect_command(tmp_path, Language.PYTHON, None).display == "python -m pytest -q"
    with pytest.raises(SecurityError):
        runner.detect_command(tmp_path, Language.JAVASCRIPT, None)
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    assert runner.detect_command(tmp_path, Language.JAVASCRIPT, None).display == "npm test"


def test_run_reports_unavailable_docker(tmp_path: Path, monkeypatch):
    runner = DockerTestRunner(
        Settings(
            data_dir=tmp_path / "data",
            workspace_dir=tmp_path / "work",
            docker_enabled=False,
        )
    )
    result = runner.run(tmp_path, Language.PYTHON, None, "baseline")
    assert result.passed is False
    assert result.skipped_reason == "Docker daemon is not available"
