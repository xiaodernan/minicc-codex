"""The workspace containment guard must have exactly one home."""

from __future__ import annotations

import ast
import pathlib
from pathlib import Path

import pytest

from minicc.tools.editor import EditError, resolve_in_workspace

REPO = pathlib.Path(__file__).resolve().parents[1]
WORKSPACE = REPO


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
    for marker in ("路径越界: 不允许绝对路径 (", " 超出 workspace 根"):
        hits = []
        for path in sorted((REPO / "minicc").rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), start=1):
                if marker in line:
                    hits.append((path.relative_to(REPO).as_posix(), lineno))
        assert len(hits) == 1, (marker, hits)
        path, lineno = hits[0]
        assert path == "minicc/tools/editor.py"
        source = (REPO / path).read_text(encoding="utf-8")
        lines = source.splitlines()
        window = "\n".join(lines[max(0, lineno - 24):lineno + 2])
        assert "def resolve_in_workspace" in window, window


def test_messages_exist_once_each():
    editor = (REPO / "minicc" / "tools" / "editor.py").read_text(encoding="utf-8")
    assert editor.count("不允许绝对路径") == 1
    assert editor.count("超出 workspace 根") == 1
    git = (REPO / "minicc" / "tools" / "git.py").read_text(encoding="utf-8")
    assert "不允许绝对路径" not in git
    assert "超出 workspace 根" not in git
    assert git.count("resolve_in_workspace(") == 1
    assert editor.count("resolve_in_workspace(") == 2
