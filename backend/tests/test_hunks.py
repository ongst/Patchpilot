import json
from pathlib import Path

from patchpilot.hunks import recount_hunks


def test_recount_correct_patch_unchanged():
    patch = (
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
    )
    assert recount_hunks(patch) == patch


def test_recount_adds_missing_trailing_newline():
    patch = (
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b"
    )
    assert recount_hunks(patch).endswith("\n")


def test_recount_strips_leading_whitespace_from_headers():
    patch = (
        "diff --git a/a.py b/a.py\n"
        "--- a/a.py\n"
        "+++ b/a.py\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
        " diff --git a/b.py b/b.py\n"
        " new file mode 100644\n"
        " --- /dev/null\n"
        " +++ b/b.py\n"
        "@@ -0,0 +1 @@\n"
        "+hello\n"
    )
    fixed = recount_hunks(patch)
    assert " diff --git" not in fixed
    assert "diff --git a/b.py b/b.py" in fixed


def test_recount_fixes_wrong_line_count():
    patch = (
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1,2 +1,5 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
    )
    fixed = recount_hunks(patch)
    assert "@@ -1,2 +1,2 @@" in fixed
    assert "return a + b" in fixed


def test_recount_multiple_hunks():
    patch = (
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1,2 +1,9 @@\n"
        " def f():\n"
        "-    return 1\n"
        "+    return 2\n"
        "@@ -5,3 +6,7 @@\n"
        " def g():\n"
        "-    return 3\n"
        "+    return 4\n"
    )
    fixed = recount_hunks(patch)
    assert "@@ -1,2 +1,2 @@" in fixed
    assert "@@ -5,2 +6,2 @@" in fixed


def test_recount_multiple_files():
    patch = (
        "diff --git a/a.py b/a.py\n"
        "--- a/a.py\n"
        "+++ b/a.py\n"
        "@@ -1,1 +1,9 @@\n"
        "-old\n"
        "+new\n"
        "diff --git a/b.py b/b.py\n"
        "--- a/b.py\n"
        "+++ b/b.py\n"
        "@@ -1,1 +1,9 @@\n"
        "-old\n"
        "+new\n"
    )
    fixed = recount_hunks(patch)
    assert fixed.count("@@ -1,1 +1,1 @@") == 2


def test_recount_fixes_saved_corrupt_patches():
    fixtures_path = Path(__file__).parent / "fixtures" / "corrupt_patches.json"
    fixtures = json.loads(fixtures_path.read_text(encoding="utf-8"))
    assert len(fixtures) == 4
    for fixture in fixtures:
        patch = fixture["patch"]
        fixed = recount_hunks(patch)
        assert fixed != patch, fixture["task_id"]
        assert recount_hunks(fixed) == fixed, fixture["task_id"]
