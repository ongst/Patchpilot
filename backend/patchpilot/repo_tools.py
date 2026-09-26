from __future__ import annotations

import ast
import re
from pathlib import Path

from patchpilot.security import is_ignored, safe_repo_path

TEXT_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mjs",
    ".py",
    ".rs",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}


class RepositoryTools:
    def __init__(self, root: Path, max_file_bytes: int = 256_000, output_limit: int = 16_000):
        self.root = root.resolve()
        self.max_file_bytes = max_file_bytes
        self.output_limit = output_limit
        self.inspected_files: set[str] = set()

    def _iter_files(self):
        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(self.root)
            if is_ignored(relative) or path.is_symlink():
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {
                "Dockerfile",
                "Makefile",
                "package-lock.json",
            }:
                continue
            try:
                if path.stat().st_size > self.max_file_bytes:
                    continue
            except OSError:
                continue
            yield path, relative.as_posix()

    def list_files(self, pattern: str = "", limit: int = 300) -> str:
        """List repository files, optionally filtering by a case-insensitive substring."""
        pattern_lower = pattern.lower()
        files = [
            relative for _, relative in self._iter_files() if pattern_lower in relative.lower()
        ]
        files.sort()
        clipped = files[: min(max(limit, 1), 500)]
        suffix = (
            f"\n... {len(files) - len(clipped)} more files" if len(files) > len(clipped) else ""
        )
        return "\n".join(clipped) + suffix

    def search_code(self, query: str, path: str = "", limit: int = 80) -> str:
        """Search text files for a literal, case-insensitive query."""
        if not query or len(query) > 200:
            raise ValueError("Search query must contain 1-200 characters")
        base = safe_repo_path(self.root, path, must_exist=True) if path else self.root
        if base.is_file():
            candidates = [(base, base.relative_to(self.root).as_posix())]
        else:
            candidates = [
                item for item in self._iter_files() if item[0] == base or base in item[0].parents
            ]

        matches: list[str] = []
        needle = query.casefold()
        for file_path, relative in candidates:
            try:
                for line_number, line in enumerate(
                    file_path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
                ):
                    if needle in line.casefold():
                        matches.append(f"{relative}:{line_number}: {line.strip()[:300]}")
                        self.inspected_files.add(relative)
                        if len(matches) >= min(max(limit, 1), 200):
                            return self._clip("\n".join(matches))
            except OSError:
                continue
        return self._clip("\n".join(matches) if matches else "No matches found")

    def read_file(self, path: str, start_line: int = 1, end_line: int = 240) -> str:
        """Read a safe range of lines from one repository text file."""
        file_path = safe_repo_path(self.root, path, must_exist=True)
        if not file_path.is_file() or file_path.stat().st_size > self.max_file_bytes:
            raise ValueError("File is not a supported text file")
        if start_line < 1 or end_line < start_line or end_line - start_line > 400:
            raise ValueError("Requested line range is invalid or exceeds 400 lines")
        relative = file_path.relative_to(self.root).as_posix()
        self.inspected_files.add(relative)
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        selected = [
            f"{index:>5} | {lines[index - 1]}"
            for index in range(start_line, min(end_line, len(lines)) + 1)
        ]
        return self._clip("\n".join(selected) or "<empty range>")

    def symbol_summary(self, limit: int = 300) -> str:
        """Build a deterministic symbol map for Python and JavaScript/TypeScript files."""
        symbols: list[str] = []
        js_symbol = re.compile(
            r"^\s*(?:export\s+)?(?:async\s+)?(?:function|class|const|let)\s+([A-Za-z_$][\w$]*)"
        )
        for file_path, relative in self._iter_files():
            try:
                source = file_path.read_text(encoding="utf-8", errors="replace")
                if file_path.suffix == ".py":
                    tree = ast.parse(source)
                    for node in tree.body:
                        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                            symbols.append(
                                f"{relative}:{node.lineno} {type(node).__name__} {node.name}"
                            )
                elif file_path.suffix in {".js", ".jsx", ".mjs", ".ts", ".tsx"}:
                    for line_number, line in enumerate(source.splitlines(), start=1):
                        match = js_symbol.match(line)
                        if match:
                            symbols.append(f"{relative}:{line_number} symbol {match.group(1)}")
                if len(symbols) >= limit:
                    break
            except (OSError, SyntaxError):
                continue
        return self._clip("\n".join(symbols) if symbols else "No supported symbols found")

    def profile(self) -> dict[str, object]:
        files = [relative for _, relative in self._iter_files()]
        python_count = sum(path.endswith(".py") for path in files)
        js_count = sum(path.endswith((".js", ".jsx", ".mjs", ".ts", ".tsx")) for path in files)
        if python_count == 0 and js_count == 0:
            language = "unknown"
        else:
            language = "python" if python_count >= js_count else "javascript"
        manifests = [
            item
            for item in (
                "pyproject.toml",
                "requirements.txt",
                "setup.py",
                "package.json",
                "package-lock.json",
            )
            if (self.root / item).exists()
        ]
        return {
            "language": language,
            "file_count": len(files),
            "python_files": python_count,
            "javascript_files": js_count,
            "manifests": manifests,
            "has_tests": any("test" in Pure.lower() for Pure in files),
        }

    def _clip(self, value: str) -> str:
        if len(value) <= self.output_limit:
            return value
        return value[: self.output_limit] + "\n... output truncated"
