"""M8-T287 — 上限是工具的，不是调用方的

三个读文件工具的规模参数都是**模型可控**的，而它们的实现要么没有上限，
要么把上限用在了"已经收完之后的显示"上：

* ``tree`` 的 ``max_depth`` / ``max_entries``：模型可以要一百万个条目、
  一百万层深；
* ``grep`` 的 ``max_matches``：同上；
* ``glob``：``MAX_GLOB_RESULTS`` 只在**结果已经全部收进内存之后**才切片——
  而那正是这个上限想避免的开销。

This door pins:

* the ceilings are the tool's, whatever the caller asks for;
* the glob walk stops **while it happens**;
* the controls: an ordinary request still works.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minicc.tools import build_registry
from minicc.tools.editor import Editor
from minicc.tools.fs import (
    MAX_GLOB_RESULTS,
    MAX_GREP_MATCHES,
    TREE_MAX_DEPTH,
    TREE_MAX_ENTRIES,
)
from minicc.tools.schemas import ToolCall


def _registry(workspace: Path) -> object:
    return build_registry(Editor(workspace))


def _tree(workspace: Path, **arguments: object) -> object:
    return _registry(workspace).execute(ToolCall(
        tool="tree", arguments={"path": ".", **arguments}, call_id="c1"
    ))


def test_the_tree_ceiling_is_the_tools_own(tmp_path: Path) -> None:
    """A caller cannot ask for a million entries."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    result = _tree(workspace, max_entries=10_000_000, max_depth=10_000_000)
    assert result.status == "error", (
        "a request above the tool's ceiling was accepted"
    )
    assert "max_depth" in result.summary or "max_entries" in result.summary, result.summary


def test_the_grep_ceiling_is_the_tools_own(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "a.txt").write_text("needle\n", encoding="utf-8")
    result = _registry(workspace).execute(ToolCall(
        tool="grep",
        arguments={"pattern": "needle", "max_matches": 10_000_000},
        call_id="c1",
    ))
    assert result.status == "error", (
        "a request above the tool's ceiling was accepted"
    )
    assert "max_matches" in result.summary or "不能超过" in result.summary, result.summary


def test_the_glob_walk_stops_while_it_happens(tmp_path: Path) -> None:
    """The cap used to slice a list that was already complete.

    The **collected** count is what shows the difference: the old walk
    gathered every match and then showed the first 200 (so the summary
    reported the full number), the new one stops after one more than the
    cap and never walks the rest of the tree.
    """
    import re

    workspace = tmp_path / "ws"
    (workspace / "many").mkdir(parents=True)
    for index in range(MAX_GLOB_RESULTS + 50):
        (workspace / "many" / f"f{index:04}.py").write_text("x = 1\n", encoding="utf-8")

    result = _registry(workspace).execute(ToolCall(
        tool="glob", arguments={"pattern": "**/*.py"}, call_id="c1"
    ))
    assert result.status == "ok", result.summary
    body = (result.head or "") + (result.tail or "")
    shown = [line for line in body.splitlines() if line.strip()]
    assert len(shown) <= MAX_GLOB_RESULTS, len(shown)

    found = re.search(r"命中 (\d+) 个", result.summary)
    assert found is not None, result.summary
    assert int(found.group(1)) <= MAX_GLOB_RESULTS + 1, (
        f"the walk collected {found.group(1)} matches; the cap is "
        f"{MAX_GLOB_RESULTS}"
    )


def test_the_ordinary_requests_still_work(tmp_path: Path) -> None:
    """The control: nothing about the ordinary path changed."""
    workspace = tmp_path / "ws"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")

    globbed = _registry(workspace).execute(ToolCall(
        tool="glob", arguments={"pattern": "**/*.py"}, call_id="c1"
    ))
    assert globbed.status == "ok"
    assert "src/app.py" in (globbed.head or "")

    treed = _tree(workspace)
    assert treed.status == "ok"
    assert "app.py" in (treed.head or "")

    grepped = _registry(workspace).execute(ToolCall(
        tool="grep", arguments={"pattern": "x = 1"}, call_id="c1"
    ))
    assert grepped.status == "ok"
    assert "app.py" in (grepped.head or "")


def test_the_declared_ceilings_are_sane() -> None:
    """The constants themselves are the contract."""
    assert MAX_GLOB_RESULTS > 0
    assert MAX_GREP_MATCHES > 0
    assert TREE_MAX_DEPTH > 0
    assert TREE_MAX_ENTRIES > 0
