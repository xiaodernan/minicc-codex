"""M8-T313 — 一次备份不是一次改动

``editor.audit_level`` 把 ``backup`` 算成 notice 级，也就是"改了工作区"。
但 a backup 只复制了一份文件，**工作区的文件没有变**。于是
``/api/audit`` 的"改了工作区"过滤器把每次写文件前自动产生的那条 backup
记录也列了进去——而变更面板（它知道得更准）根本不列 backup。

两处对"这次调用改了工作区吗"各有一份答案，于是分叉。

This door pins:

* a backup is not a workspace change;
* the two faces answer the same question the same way.
"""

from __future__ import annotations

from pathlib import Path

from minicc.changes import _CHANGING_AUDIT_ACTIONS
from minicc.tools.editor import Editor, audit_level


def test_a_backup_is_not_a_workspace_change() -> None:
    assert audit_level("backup", "→ notes.md.2026…") == "info", (
        "a backup was reported as a workspace change"
    )


def test_a_real_change_is_still_a_workspace_change() -> None:
    """The control: the level means what it says."""
    for action in ("write", "edit", "delete", "move"):
        assert audit_level(action, "") == "notice", action


def test_a_read_is_not_a_workspace_change() -> None:
    assert audit_level("read", "") == "info"


def test_the_two_faces_answer_the_same_question() -> None:
    """One definition, two consumers."""
    from minicc.tools.editor import _MUTATING_ACTIONS

    assert set(_CHANGING_AUDIT_ACTIONS) == set(_MUTATING_ACTIONS), (
        "the change panel and the audit level disagree about what changed "
        "the workspace"
    )


def test_a_write_produces_no_notice_for_its_backup(tmp_path: Path) -> None:
    """The observable consequence: the filter used to list the copy."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    editor = Editor(workspace, audit_path=workspace / ".minicc" / "audit.jsonl")
    editor.write_file("a.py", "x = 1\n")

    levels = [
        audit_level(action, detail)
        for action, detail in _audit_lines(workspace / ".minicc" / "audit.jsonl")
    ]
    assert "notice" in levels, "the write was not reported as a change"
    assert levels.count("notice") == 1, (
        f"the write produced {levels.count('notice')} change-level audit lines"
    )


def _audit_lines(path: Path) -> list[tuple[str, str]]:
    import json

    return [
        (
            str(json.loads(line).get("action") or ""),
            str(json.loads(line).get("detail") or ""),
        )
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
