import subprocess
from pathlib import Path

import pytest
from patchpilot.git_service import GitService
from patchpilot.patching import validate_patch, validate_patch_structure
from patchpilot.security import SecurityError


def init_repo(path: Path) -> GitService:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    (path / "app.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-m",
            "initial",
        ],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "switch", "-c", "patchpilot/run-1234abcd"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    return GitService()


def good_patch() -> str:
    return """diff --git a/app.py b/app.py
index 6fc75a1..6c5e0df 100644
--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
"""


def test_patch_validation_and_application(tmp_path: Path):
    git = init_repo(tmp_path)
    summary = validate_patch(git, tmp_path, good_patch(), max_files=8, max_changed_lines=800)
    assert summary.files == ["app.py"]
    git.apply_patch(tmp_path, good_patch())
    assert "a + b" in (tmp_path / "app.py").read_text(encoding="utf-8")


def test_patch_rejects_path_escape(tmp_path: Path):
    patch = """diff --git a/../outside.py b/../outside.py
--- a/../outside.py
+++ b/../outside.py
@@ -0,0 +1 @@
+bad
"""
    with pytest.raises(SecurityError):
        validate_patch_structure(tmp_path, patch)


def test_patch_limits_changed_files(tmp_path: Path):
    patch = "\n".join(
        f"diff --git a/f{i}.py b/f{i}.py\n--- a/f{i}.py\n+++ b/f{i}.py\n@@ -1 +1 @@\n-a\n+b"
        for i in range(3)
    )
    with pytest.raises(SecurityError):
        validate_patch_structure(tmp_path, patch, max_files=2)


def test_git_rejects_write_on_default_branch(tmp_path: Path):
    git = init_repo(tmp_path)
    subprocess.run(["git", "switch", "main"], cwd=tmp_path, check=True, capture_output=True)
    with pytest.raises(SecurityError):
        git.apply_check(tmp_path, good_patch())
