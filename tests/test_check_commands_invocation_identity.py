"""M8-T766 — ``minicc/agent/check_commands.py`` 的命令切分/身份转换。

这个模块是验证命令的"切成 argv"和"归一显示变体"的唯一家，零同名测试
（模块→测试映射发现）。

1. `command_parts`：引号/转义/未闭合引号；
2. `checker_invocation`：`python -[B...] -m pytest` 前缀、.exe 去尾、
   未知 runner → 原样；
3. `PYTHON_TEST_RUNNERS`：{pytest, unittest}；
4. `verification_identity`：`pytest -q` 与 `python -m pytest -q` 归一为同一元组——
   "同一选择集永不改"的集合论。
"""

from __future__ import annotations

import pytest

from minicc.agent import check_commands as cc


def test_command_parts_basic_split():
    assert cc.command_parts("pytest -q tests/x.py") == ["pytest", "-q", "tests/x.py"]


def test_command_parts_honors_quotes():
    assert cc.command_parts("echo 'a b'") == ["echo", "a b"]
    assert cc.command_parts('echo "a b"') == ["echo", "a b"]


def test_command_parts_empty_quoted_argument_is_a_token():
    assert cc.command_parts('echo ""') == ["echo", ""]


def test_command_parts_backslash_escapes_the_matching_quote():
    assert cc.command_parts('echo "a\\"b"') == ["echo", 'a"b']


def test_command_parts_unclosed_quote_raises():
    with pytest.raises(ValueError):
        cc.command_parts('echo "unclosed')


def test_command_parts_no_shell_evaluation():
    # 切分不执行 shell；`|` 只是普通字符
    assert cc.command_parts("echo hi|cat") == ["echo", "hi|cat"]


def test_checker_invocation_python_m():
    assert cc.checker_invocation("python -m pytest -q") == ("pytest", ["-q"])


def test_checker_invocation_python_with_interpreter_flags():
    assert cc.checker_invocation("python -I -B -m pytest tests/x.py") == (
        "pytest",
        ["tests/x.py"],
    )


def test_checker_invocation_windows_python_exe():
    assert cc.checker_invocation(r"C:\tools\python.exe -m pytest tests/") == (
        "pytest",
        ["tests/"],
    )


def test_checker_invocation_bare_pytest_passes_through():
    assert cc.checker_invocation("pytest -q tests/x.py") == (
        "pytest",
        ["-q", "tests/x.py"],
    )


def test_checker_invocation_non_module_python_is_not_a_checker():
    assert cc.checker_invocation("python script.py") == ("", [])


def test_python_test_runners_are_pytest_and_unittest():
    assert cc.PYTHON_TEST_RUNNERS == frozenset({"pytest", "unittest"})


def test_verification_identity_unifies_invocation_variants():
    direct = cc.verification_identity("pytest -q tests/x.py")
    via_module = cc.verification_identity("python -m pytest -q tests/x.py")
    assert direct == via_module == ("pytest", "tests/x.py")


def test_verification_identity_normalizes_path_separators_and_prefix():
    assert cc.verification_identity("pytest ./tests/x.py") == ("pytest", "tests/x.py")
    assert cc.verification_identity("pytest .\\tests\\x.py") == ("pytest", "tests/x.py")


def test_verification_identity_drops_verbosity_flags_only():
    identity = cc.verification_identity("pytest -q -v -vv -vvv --quiet --verbose tests/x.py")
    assert identity == ("pytest", "tests/x.py")


def test_verification_identity_non_test_runner_falls_back_to_split():
    assert cc.verification_identity("make test") == ("make", "test")
