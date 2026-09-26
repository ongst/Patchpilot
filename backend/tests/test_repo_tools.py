from pathlib import Path

import pytest
from patchpilot.repo_tools import RepositoryTools
from patchpilot.security import SecurityError


def test_repository_tools_profile_search_and_read(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "service.py").write_text(
        "class Service:\n    def calculate(self, value):\n        return value + 1\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    tools = RepositoryTools(tmp_path)

    assert "src/service.py" in tools.list_files()
    assert "return value + 1" in tools.search_code("value + 1")
    assert "class Service" in tools.read_file("src/service.py", 1, 2)
    assert "ClassDef Service" in tools.symbol_summary()
    assert tools.profile()["language"] == "python"
    assert "src/service.py" in tools.inspected_files


def test_repository_tools_ignore_dependencies_and_escape(tmp_path: Path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "bad.js").write_text("secret", encoding="utf-8")
    tools = RepositoryTools(tmp_path)
    assert "bad.js" not in tools.list_files()
    with pytest.raises(SecurityError):
        tools.read_file("../outside.txt")
