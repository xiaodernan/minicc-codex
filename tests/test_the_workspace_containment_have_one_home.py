"""The workspace containment guard must have exactly one home."""

from __future__ import annotations

import ast
import pathlib
from pathlib import Path

import pytest

from minicc.tools.editor import (
    PATH_ESCAPED_PREFIX,
    EditError,
    path_escaped_workspace,
    resolve_in_workspace,
)

REPO = pathlib.Path(__file__).resolve().parents[1]
WORKSPACE = REPO
HOME = "minicc/tools/editor.py"
BUILDER = "path_escaped_workspace"

DETAILS = ("不允许绝对路径 (", " 超出 workspace 根")


def _trees():
    for path in sorted((REPO / "minicc").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path, ast.parse(path.read_bytes().decode("utf-8"))


def _carriers(needle: str) -> list[str]:
    """Every string constant carrying the needle - f-string parts included."""
    hits = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if needle in node.value:
                    hits.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}")
    return hits


def _calls(name: str) -> list[str]:
    hits = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name:
                hits.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}")
    return hits


def test_home_resolves_a_relative_path_inside():
    assert resolve_in_workspace(WORKSPACE, "minicc/tools/editor.py") == (
        WORKSPACE / "minicc/tools/editor.py"
    ).resolve()


def test_home_rejects_a_relative_escape():
    with pytest.raises(EditError, match="超出 workspace 根"):
        resolve_in_workspace(WORKSPACE, "../outside")


def test_home_rejects_an_absolute_path():
    with pytest.raises(EditError, match="不允许绝对路径"):
        resolve_in_workspace(WORKSPACE, str(WORKSPACE / "minicc"))


def test_census_exactly_one_guard_and_it_is_the_home():
    """The two reasons a path is out live in the home, once each."""
    for marker in DETAILS:
        hits = _carriers(marker)
        assert len(hits) == 1, (marker, hits)
        path, lineno = hits[0].split(":")
        assert path == HOME, (marker, hits)
        source = (REPO / path).read_text(encoding="utf-8")
        lines = source.splitlines()
        window = "\n".join(lines[max(0, int(lineno) - 24):int(lineno) + 2])
        assert "def resolve_in_workspace" in window, window


def test_the_prefix_literal_is_spelled_exactly_once():
    """Equality, not containment: ``快照路径越界: `` contains the prefix too.

    A hand-written ``f"路径越界: {base}"`` parses to the constant part
    ``"路径越界: "``, which *equals* the prefix - so the equality census
    still catches it, while the snapshot and worktree guards, whose heads
    differ, stay out of it.
    """
    hits = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == PATH_ESCAPED_PREFIX:
                hits.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}")
    assert len(hits) == 1, hits
    assert hits[0].startswith(f"{HOME}:"), hits


def test_no_other_constant_starts_with_the_prefix():
    """A hand-written copy is the drift; a longer spelling is a different guard.

    ``快照路径越界: `` (snapshots) and ``worktree 路径越界`` (worktree)
    both *contain* the prefix but neither starts with it - they are separate
    guards with their own homes, so the test discriminates on the head.
    """
    strays = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value.startswith(PATH_ESCAPED_PREFIX) and node.value != PATH_ESCAPED_PREFIX:
                    strays.append((path.as_posix(), node.lineno, node.value[:40]))
    assert strays == [], strays


def test_the_builder_is_defined_exactly_once():
    definitions = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == BUILDER:
                definitions.append(path.relative_to(REPO).as_posix())
    assert definitions == [HOME], definitions


def test_the_builder_is_called_from_every_site_that_refuses_a_path():
    """Six refusals: two in the home, three in fs, one in web."""
    sites = _calls(BUILDER)
    assert len(sites) == 6, sites
    assert sum(site.startswith(f"{HOME}:") for site in sites) == 2, sites
    assert sum(site.startswith("minicc/tools/fs.py:") for site in sites) == 3, sites
    assert sum(site.startswith("minicc/web.py:") for site in sites) == 1, sites


def test_the_outside_sites_read_the_builder_from_the_home():
    for rel in ("minicc/tools/fs.py", "minicc/web.py"):
        for path, tree in _trees():
            if path.relative_to(REPO).as_posix() != rel:
                continue
            names = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    names.update(alias.name for alias in node.names)
            assert BUILDER in names, rel
            return
        raise AssertionError(f"{rel} not found")


def test_the_builder_is_the_prefix_then_the_reason():
    assert path_escaped_workspace("../x") == "路径越界: ../x"
    assert path_escaped_workspace("") == PATH_ESCAPED_PREFIX


def test_messages_exist_once_each():
    editor = (REPO / "minicc" / "tools" / "editor.py").read_text(encoding="utf-8")
    assert editor.count("不允许绝对路径") == 1
    assert editor.count("超出 workspace 根") == 1
    git = (REPO / "minicc" / "tools" / "git.py").read_text(encoding="utf-8")
    assert "不允许绝对路径" not in git
    assert "超出 workspace 根" not in git
    assert git.count("resolve_in_workspace(") == 1
    assert editor.count("resolve_in_workspace(") == 2
