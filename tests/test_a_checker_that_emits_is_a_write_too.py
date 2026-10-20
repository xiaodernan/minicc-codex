"""M8-T312 — 检查器自己会不会**产出东西**，两个判据要一起回答

`is_verification_evidence` 说 `tsc` 是**检查**，`command_may_modify_workspace`
说它**不是写**。两条合起来的意思是："跑 `tsc` 既是一次验证、又没有改动任何
东西"。

但 `tsc` 不加 `--noEmit` 时会**把 JavaScript 产出到源文件旁边**——那不是
`.mypy_cache` 那种**缓存**，那是**真实的构建产物**。于是：

* 任务被标成 `safe_readonly`（"这个任务没改过东西"），而它刚刚写出了一批
  `.js`；
* "写后要有客观证据"这条规则**不适用**（因为没被认成写），于是那份构建产物
  从来没被检查过；
* 而产出它的正是**那个本该做检查的检查**——检查与被检查的东西是同一批文件。

`--noEmit` 的 `tsc` 才是纯检查 ✓（它不写任何东西）。

本门禁钉住：会产出的 `tsc` 是写；`--noEmit` 的不是；两个判据一起回答。
"""

from __future__ import annotations

import pytest

from minicc.agent.tool_policy import command_may_modify_workspace, is_verification_evidence


@pytest.mark.parametrize(
    "command",
    [
        "tsc",
        "tsc -p tsconfig.json",
        "npx tsc",
        "npx tsc -p tsconfig.json",
    ],
)
def test_a_checker_that_emits_is_a_write(command: str) -> None:
    """The emitted files are build output, not a cache."""
    assert command_may_modify_workspace(command) is True, command


@pytest.mark.parametrize(
    "command",
    [
        "tsc --noEmit",
        "npx tsc --noEmit",
        "tsc --noEmit --pretty false",
    ],
)
def test_a_checker_that_does_not_emit_is_not_a_write(command: str) -> None:
    """The control: ``--noEmit`` is a pure check."""
    assert command_may_modify_workspace(command) is False, command


def test_the_two_predicates_agree_about_the_side_effect() -> None:
    """``tsc`` is evidence **and** (when it emits) a write.

    They answer two different questions - "is this a check?" and "does this
    change the workspace?" - but they must not contradict each other about
    the same call.
    """
    assert is_verification_evidence("bash", {"command": "tsc"}, "ok") is True
    assert command_may_modify_workspace("tsc") is True

    assert is_verification_evidence("bash", {"command": "tsc --noEmit"}, "ok") is True
    assert command_may_modify_workspace("tsc --noEmit") is False


def test_the_other_checkers_are_unchanged() -> None:
    """The control: the other checkers leave only caches behind."""
    for command in ("pyright", "mypy pkg", "pytest -q", "python -m compileall pkg"):
        assert command_may_modify_workspace(command) is False, command
        assert is_verification_evidence("bash", {"command": command}, "ok") is True, command
