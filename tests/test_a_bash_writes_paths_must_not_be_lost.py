"""M8-T314 — bash 写入的改动路径不能再丢

一次 bash 写入（``sed -i``、``python patch.py``、``> file``）不带 ``path``。
于是从事件重建改动集合的两处——验证计划与修复范围——都拿到**空集**：
验证计划是为"没有改动"生成的，修复范围也是空的。

循环自己知道改了什么（M8-T281 之后它用 git 问出来了），所以那些路径
在 ``verification_required`` 这条 trace 里，下游只要读它。

This door pins:

* the verification plan sees a bash write's paths;
* the repair scope sees them too;
* the controls: a normal write's path is still there, and a read is not.
"""

from __future__ import annotations

from typing import Any

from minicc.agent.repair import repair_scope
from minicc.agent.verification_plan import changed_paths_from_events

BASH_TRACE: dict[str, Any] = {
    "kind": "trace",
    "code": "verification_required",
    "status": "ok",
    "detail": {"changed_paths": ["app.py", "notes.md"]},
}
WRITE_EVENT: dict[str, Any] = {
    "kind": "tool",
    "name": "write_file",
    "status": "ok",
    "write": True,
    "path": "src/app.py",
}
READ_EVENT: dict[str, Any] = {
    "kind": "tool",
    "name": "read_file",
    "status": "ok",
    "write": False,
    "path": "README.md",
}


def test_the_verification_plan_sees_a_bash_writes_paths() -> None:
    paths = changed_paths_from_events([BASH_TRACE])
    assert "app.py" in paths, f"the bash write's paths were lost: {paths}"
    assert "notes.md" in paths


def test_the_repair_scope_sees_a_bash_writes_paths() -> None:
    scope = repair_scope([BASH_TRACE], {"failed_tests": ["test_app"]})
    assert "app.py" in scope["changed_paths"], scope
    assert "app.py" in scope["repair_targets"], scope


def test_a_normal_write_is_still_reported() -> None:
    """The control: the ordinary path is untouched."""
    paths = changed_paths_from_events([WRITE_EVENT])
    assert paths == ["src/app.py"]


def test_a_read_is_not_a_change() -> None:
    """The control: a read contributes nothing."""
    assert changed_paths_from_events([READ_EVENT]) == []


def test_the_two_faces_agree() -> None:
    """One source of truth for "what changed"."""
    events = [BASH_TRACE, WRITE_EVENT, READ_EVENT]
    paths = changed_paths_from_events(events)
    scope = repair_scope(events, {"failed_tests": []})
    assert set(scope["changed_paths"]) == set(paths), (
        "the verification plan and the repair scope disagree about the changes"
    )
