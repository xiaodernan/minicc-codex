"""M8-T505 — 未知审计级别判词两个家：levels 与 min_level 各拼一句

「未知审计级别: X（可选：…）」在 `web.py` 的 `_audit_level_filter` 里有
两个家：levels 列表校验和 min_level 下限校验。两处逐字相同（只有主语不
同：raw vs min_level）。一个未知级别从哪个参数进来，读到的就是哪份拼写
——一处改了措词其余没跟上，没有任何测试会红。

家安在 `minicc/web.py` 模块层，紧挨 `_audit_level_filter`——两个调用点
都在它里面。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/web.py"
SENTENCE = "未知审计级别: （可选：）"


def _literal_shapes():
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        inside_fstring: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                for child in ast.iter_child_nodes(node):
                    inside_fstring.add(id(child))
        for node in ast.walk(tree):
            if id(node) in inside_fstring:
                continue
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                yield path, node.lineno, node.value
            elif isinstance(node, ast.JoinedStr):
                parts = [
                    part.value
                    for part in node.values
                    if isinstance(part, ast.Constant) and isinstance(part.value, str)
                ]
                yield path, node.lineno, "".join(parts)


def test_the_home_pins_the_sentence() -> None:
    from minicc.web import AUDIT_LEVELS, unknown_audit_level_message

    expected = f"未知审计级别: Bogus（可选：{', '.join(AUDIT_LEVELS)}）"
    assert unknown_audit_level_message("Bogus") == expected


def test_the_sentence_is_spelled_exactly_once_in_the_package() -> None:
    offenders = [
        f"{path.relative_to(REPO).as_posix()}:{lineno}"
        for path, lineno, text in _literal_shapes()
        if text == SENTENCE
    ]
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the unknown-audit-level sentence is spelled by hand outside its one "
        "home: " + ", ".join(offenders)
    )


def test_both_parameters_ask_the_home() -> None:
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("unknown_audit_level_message(") == 3, (
        "web.py asks the home "
        f"{source.count('unknown_audit_level_message(')} times, expected 3 "
        "(one definition plus two parameters)"
    )


def test_the_levels_parameter_emits_the_homes_sentence() -> None:
    from minicc.web import AUDIT_LEVELS, _audit_level_filter

    with pytest.raises(ValueError) as excinfo:
        _audit_level_filter(levels=["Bogus"])
    # The verdict names what the caller wrote, not the casefolded lookup
    # name - a casefolded subject is a subject the user cannot grep for.
    assert str(excinfo.value) == (
        f"未知审计级别: Bogus（可选：{', '.join(AUDIT_LEVELS)}）"
    ), excinfo.value


def test_the_min_level_parameter_emits_the_homes_sentence() -> None:
    from minicc.web import AUDIT_LEVELS, _audit_level_filter

    with pytest.raises(ValueError) as excinfo:
        _audit_level_filter(min_level="Bogus")
    assert str(excinfo.value) == (
        f"未知审计级别: Bogus（可选：{', '.join(AUDIT_LEVELS)}）"
    ), excinfo.value
