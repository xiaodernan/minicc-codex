"""M8-T507 — 测试文件名判词三个家：test_ 前缀与 _test.py 后缀成对出现

「名字是测试文件吗」（`test_` 前缀 **或** `_test.py` 后缀）有三个家：
`test_selection.py` 的目录遍历（`_test_files`）、`test_selection.py` 的收
敛路径匹配、`impact.py` 的 `_is_test`。三处逐字相同。哪处改了形状其余没
跟上，选测试的集合就悄悄变了——没有任何测试会红。

家安在 `minicc/agent/test_selection.py`——「选哪些测试」正是它的职责，
impact 引用它不成环（agent 包不依赖 impact）。同族的「函数名以 test_ 开
头」（pytest 函数识别）是另一个事实，不进来。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/agent/test_selection.py"


def _paired_shapes() -> list[str]:
    """Every ``startswith("test_") or endswith("_test.py")`` pair."""
    sites: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.BoolOp) or not isinstance(node.op, ast.Or):
                continue
            spells: dict[str, str] = {}
            for value in node.values:
                if not isinstance(value, ast.Call):
                    continue
                func = value.func
                if not isinstance(func, ast.Attribute) or not value.args:
                    continue
                arg = value.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    spells[func.attr] = arg.value
            if spells.get("startswith") == "test_" and spells.get("endswith") == "_test.py":
                sites.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}")
    return sites


def test_the_home_pins_the_predicate() -> None:
    from minicc.agent.test_selection import is_test_filename

    assert is_test_filename("test_a.py") is True
    assert is_test_filename("a_test.py") is True
    assert is_test_filename("a.py") is False
    # The predicate owns the name shape only; the ".py" check stays at the
    # call site (the walker needs it, the impact analysis does not).
    assert is_test_filename("test_a.txt") is True


def test_the_pair_is_spelled_exactly_once_in_the_package() -> None:
    offenders = _paired_shapes()
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the test-filename pair is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )


def test_all_three_sites_ask_the_home() -> None:
    for module, expected in (("agent/test_selection.py", 3), ("impact.py", 1)):
        source = (REPO / "minicc" / module).read_text(encoding="utf-8")
        assert source.count("is_test_filename(") == expected, (
            f"{module} asks the home {source.count('is_test_filename(')} "
            f"times, expected {expected}"
        )


def test_the_test_walker_yields_only_test_files(tmp_path: Path) -> None:
    from minicc.agent.test_selection import _test_files

    tests = tmp_path / "tests"
    (tests / "sub").mkdir(parents=True)
    for name in ("test_a.py", "b.py", "test_c.py", "sub/test_d.py", "notes.md"):
        (tests / name).write_text("x = 1\n", encoding="utf-8")
    found = sorted(p.name for p in _test_files(tests))
    assert found == ["test_a.py", "test_c.py", "test_d.py"], found


def test_the_impact_analysis_classifies_by_the_home(tmp_path: Path) -> None:
    from minicc.impact import _is_test

    assert _is_test("tests/test_x.py") is True
    # The ``_test.py`` suffix half of the pair, not just the ``test_`` prefix.
    assert _is_test("tests/a_test.py") is True
    assert _is_test("src/a_test.py") is False
    assert _is_test("src/a.py") is False
