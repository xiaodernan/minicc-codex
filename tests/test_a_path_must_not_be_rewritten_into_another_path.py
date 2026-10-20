"""M8-T299 — 一个路径不能被"改成另一个路径"去检查

验证命令把改动路径拼进 shell 命令，路径用双引号包起来。原来双引号是
**被删掉**的：

    "we"ird.py"  ->  "weird.py"

于是检查跑在了一个**根本不存在的文件**上，失败信息是"文件找不到"——
而模型拿到的那条路径从来就不是被检查过的那条，所以它**修不好**。

本门禁钉住：无法可移植地加引号的路径被**拒绝**（而不是被改写），并且
它不会把整份验证计划带崩。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minicc.agent.verification_plan import (
    _quote,
    build_verification_plan,
    safe_verification_command,
)


def test_a_path_with_a_quote_is_refused_not_rewritten() -> None:
    """The old behaviour silently pointed at a different file."""
    with pytest.raises(ValueError):
        _quote('we"ird.py')


def test_an_ordinary_path_is_still_quoted() -> None:
    """The control: the ordinary path is unchanged."""
    assert _quote("src/app.py") == '"src/app.py"'


def test_a_plan_skips_an_unquotable_path_instead_of_dying(tmp_path: Path) -> None:
    """One bad path must not take the whole plan down."""
    root = tmp_path / "ws"
    (root / "tests").mkdir(parents=True)
    (root / "app.py").write_text("x = 1\n", encoding="utf-8")
    (root / "tests" / "test_app.py").write_text(
        "def test_app():\n    assert True\n", encoding="utf-8"
    )
    weird = root / 'we"ird.py'
    try:
        weird.write_text("y = 2\n", encoding="utf-8")
    except OSError:
        pytest.skip("this platform does not allow a quote in a file name")

    plan = build_verification_plan(root, ["app.py", 'we"ird.py'])
    for command in plan.commands:
        assert 'we"ird.py' not in command.command, (
            f"the unquotable path was checked anyway: {command.command}"
        )


def test_a_command_with_a_quote_is_not_safe() -> None:
    """A double quote ends the quoted argument - it is a metacharacter."""
    assert safe_verification_command('python -m pytest -q "we"ird.py"') is False


def test_an_ordinary_command_is_still_safe() -> None:
    """The control: the ordinary path is unchanged."""
    assert safe_verification_command("python -m pytest -q") is True
