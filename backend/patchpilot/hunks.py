from __future__ import annotations

import re

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

_STRUCTURAL_PREFIXES = (
    "diff --git ",
    "new file mode ",
    "deleted file mode ",
    "index ",
    "--- ",
    "+++ ",
    "@@ ",
)


def _strip_leading_whitespace(line: str) -> str:
    stripped = line.lstrip()
    if stripped.startswith(_STRUCTURAL_PREFIXES):
        return stripped
    return line


def recount_hunks(patch: str) -> str:
    """Normalize a model-generated unified diff before ``git apply``.

    - strips leading whitespace from structural lines (``diff --git``, ``---``,
      ``+++``, ``@@``, ``index``, ...) that the model may have indented;
    - rewrites hunk headers so their declared line counts match the body;
    - adds a trailing newline if one is missing.

    Start lines and body lines are otherwise preserved verbatim.
    """
    lines = [
        _strip_leading_whitespace(line)
        for line in patch.replace("\r\n", "\n").splitlines(keepends=True)
    ]
    result: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        match = _HUNK_HEADER.match(line)
        if match is None:
            result.append(line)
            index += 1
            continue

        old_start = int(match.group(1))
        new_start = int(match.group(3))
        declared_old = int(match.group(2)) if match.group(2) is not None else 1
        declared_new = int(match.group(4)) if match.group(4) is not None else 1

        counted_old = 0
        counted_new = 0
        body_lines: list[str] = []
        index += 1
        while index < len(lines):
            body = lines[index]
            if _HUNK_HEADER.match(body) or body.startswith("diff --git "):
                break
            body_lines.append(body)
            if body.startswith("+") and not body.startswith("+++"):
                counted_new += 1
            elif body.startswith("-") and not body.startswith("---"):
                counted_old += 1
            elif body.startswith(" "):
                counted_old += 1
                counted_new += 1
            # Other lines (e.g. "\ No newline at end of file") are not counted.
            index += 1

        if counted_old == declared_old and counted_new == declared_new:
            result.append(line)
        else:
            result.append(f"@@ -{old_start},{counted_old} +{new_start},{counted_new} @@\n")
        result.extend(body_lines)

    output = "".join(result)
    if not output.endswith("\n"):
        output += "\n"
    return output
