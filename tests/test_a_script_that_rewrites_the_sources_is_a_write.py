"""M8-T324 — 一个"检查脚本"如果会**重写被检查的文件**，它就是一次写

`npm run format`（prettier --write）与 `npm run lint:fix`（eslint --fix）会
**改写它们检查的那些源文件**。而：

* `is_verification_evidence` 把 `format` 认成**检查**；
* `command_may_modify_workspace` 认不出它会改写 → 说是**不是写**。

于是那个"检查"在**改**它本该**验证**的东西，而任务仍然被标成
`safe_readonly`——"写后要有客观证据"这条规则**不适用**（因为没被认成写）。

而检查型的拼写（`--check`、`:check`）**不**改写任何东西，必须仍然是"不是写"。

本门禁钉住：会重写的脚本是写；检查型的拼写不是。
"""

from __future__ import annotations

import pytest

from minicc.agent.tool_policy import command_may_modify_workspace, is_verification_evidence


@pytest.mark.parametrize(
    "command",
    [
        "npm run format",
        "npm run fmt",
        "npm run format:fix",
        "npm run lint:fix",
        "npm run lint -- --fix",
        "yarn format",
        "pnpm run format",
    ],
)
def test_a_script_that_rewrites_the_sources_is_a_write(command: str) -> None:
    """The check rewrote the change it was supposed to verify."""
    assert command_may_modify_workspace(command) is True, command


@pytest.mark.parametrize(
    "command",
    [
        "npm run format:check",
        "npm run format -- --check",
        "npm run lint",
        "npm run lint:check",
        "npm test",
        "npm run check:web",
        "yarn test",
    ],
)
def test_the_check_only_spellings_are_not_writes(command: str) -> None:
    """The control: a check that changes nothing."""
    assert command_may_modify_workspace(command) is False, command


def test_the_two_predicates_agree_about_the_side_effect() -> None:
    """``npm run lint -- --fix`` is evidence **and** a write.

    It answers two different questions - "is this a check?" and "does this
    change the workspace?" - but it must not contradict itself about the
    same call: the script name is ``lint`` (a check), and the ``--fix`` it
    passes rewrites the very files it looked at.  The evidence predicate
    reads the script name; the write predicate reads the whole command.
    """
    assert is_verification_evidence("bash", {"command": "npm run lint -- --fix"}, "ok") is True
    assert command_may_modify_workspace("npm run lint -- --fix") is True

    # The same script without ``--fix`` is a pure check.
    assert is_verification_evidence("bash", {"command": "npm run lint"}, "ok") is True
    assert command_may_modify_workspace("npm run lint") is False

    # ``format`` is not claimed to be a check at all - it is simply a write.
    assert is_verification_evidence("bash", {"command": "npm run format"}, "ok") is False
    assert command_may_modify_workspace("npm run format") is True


def test_the_build_script_is_still_a_write() -> None:
    """The control: the ordinary case is unchanged."""
    assert command_may_modify_workspace("npm run build") is True
