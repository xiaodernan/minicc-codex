"""M8-T302 — `~` 也是一个"工作区之外"

安全模式自动放行的命令只有"窄口径的 pytest 调用"，而它的路径参数必须留在
工作区内。绝对路径、`..`、盘符、UNC 都被拒了——**唯独 `~` 没有**。

于是 `pytest ~/secrets` 被自动放行：在 POSIX 上 shell 把它展开成 home 目录，
pytest 于是去**import** 那里找到的测试模块——那是工作区之外的任意代码执行，
而这个模式的全部承诺就是"只读工作区里的东西"。

本门禁钉住：`~` 被拒；别的照旧。
"""

from __future__ import annotations

import pytest

from minicc.tools.bash import is_readonly_command


@pytest.mark.parametrize(
    "command",
    [
        "pytest ~/secrets",
        "pytest ~/private_tests",
        "python -m pytest -q ~/secrets",
        "pytest tests ~/secrets",
        "pytest ~",
        "pytest ~user/secrets",
    ],
)
def test_a_home_reference_is_refused(command: str) -> None:
    """The home directory is outside the workspace."""
    assert is_readonly_command(command) is False, (
        f"a home-directory reference was auto-approved: {command!r}"
    )


@pytest.mark.parametrize(
    "command",
    [
        "pytest tests",
        "pytest .",
        "python -m pytest -q tests/",
        "pytest -q tests/test_app.py",
    ],
)
def test_the_ordinary_calls_are_still_approved(command: str) -> None:
    """The control: the narrow safe mode is unchanged."""
    assert is_readonly_command(command) is True, command


@pytest.mark.parametrize(
    "command",
    [
        "pytest /etc",
        "pytest ../outside",
        "pytest C:/Windows",
        "pytest -p evil_module",
        "pytest -c /tmp/other.ini",
        "rm -rf /",
    ],
)
def test_the_other_escapes_are_still_refused(command: str) -> None:
    """The control: the other ways out keep their verdict."""
    assert is_readonly_command(command) is False, command
