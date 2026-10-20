"""M8-T303 — 验证证据的判据是"可执行名"，不是"命令里有没有这个词"

`minicc/agent/tool_policy.py` 里长期存在一个 `VERIFY_COMMAND_MARKERS` 标记表
（"pytest"、"unittest"、"npm test"…），它看起来就是"什么算验证证据"的规则。

但实现从来**没有**用过它：真正的判据是 `checker_invocation` 取出的
**可执行名**与一份白名单比对。于是那份表是一份**过时的第二份规则**，
而且它宣传的是一条**并不存在**的规则——按它的读法，"pytest" 出现在命令里
就够了（`echo pytest` 算不算？）。

过时的第二份规则比没有规则更糟：读代码的人会照着它理解系统。

本门禁钉住：判据是**可执行名**；标记表不再存在。
"""

from __future__ import annotations

import pytest

from minicc.agent import tool_policy
from minicc.agent.tool_policy import is_verification_evidence


@pytest.mark.parametrize(
    "command",
    [
        "echo pytest",
        "grep pytest tests",
        "cat pytest.log",
        "echo unittest",
        "echo mypy",
    ],
)
def test_a_mention_of_a_checker_is_not_evidence(command: str) -> None:
    """The word is not the rule; the executable is."""
    assert is_verification_evidence("bash", {"command": command}, "ok") is False, (
        f"a command that merely mentions a checker counted as evidence: {command!r}"
    )


@pytest.mark.parametrize(
    "command",
    [
        "python -m pytest -q",
        "pytest -q tests",
        "npm test",
        "ruff check .",
        "node --check app.js",
        "mypy pkg",
    ],
)
def test_a_real_checker_is_evidence(command: str) -> None:
    """The control: the ordinary path is unchanged."""
    assert is_verification_evidence("bash", {"command": command}, "ok") is True, command


def test_the_stale_marker_table_is_gone() -> None:
    """A stale second copy of a rule is worse than no copy."""
    assert not hasattr(tool_policy, "VERIFY_COMMAND_MARKERS"), (
        "the unused marker table is back; it advertises a rule that is not "
        "the rule"
    )
    assert "VERIFY_COMMAND_MARKERS" not in tool_policy.__all__
