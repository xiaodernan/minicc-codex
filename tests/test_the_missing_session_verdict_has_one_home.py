"""M8-T495 — 会话不存在判词三个家：_read_payload / rewind / rewind_to_user

「会话不存在: X」在 `session.py` 里有三个家：`_read_payload`（所有读取的
兜底门）、`rewind`、`rewind_to_user_index`，三处逐字相同。模型从哪扇门进
去，读到的就是哪份拼写——一处改了措词其余两处没跟上，没有任何测试会红
（T489/T494：同文件重复是最危险的重复）。

家安在 `minicc/session.py` 模块层，紧挨 `SessionError`——它要报告的异常
类。三处都传 `self.path.name`（会话文件名），所以家只收一个参数。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/session.py"
VERDICT = "会话不存在"


def _sites(fragment: str) -> list[str]:
    """Every string literal containing the fragment - f-string parts joined."""
    found: list[str] = []
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
            texts: list[str] = []
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                texts = [node.value]
            elif isinstance(node, ast.JoinedStr):
                texts = [
                    "".join(
                        part.value
                        for part in node.values
                        if isinstance(part, ast.Constant) and isinstance(part.value, str)
                    )
                ]
            for text in texts:
                if fragment in text:
                    found.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}")
    return found


def test_the_home_pins_the_sentence() -> None:
    from minicc.session import missing_session_message

    assert missing_session_message("abc123.json") == "会话不存在: abc123.json"


def test_the_verdict_is_spelled_exactly_once_in_the_package() -> None:
    offenders = _sites(VERDICT)
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the session-missing verdict is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )


def test_all_three_gates_ask_the_home() -> None:
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("missing_session_message(") == 4, (
        "the definition plus the three gates are the only spellings, found "
        f"{source.count('missing_session_message(')}"
    )


def test_the_payload_backstop_raises_the_homes_sentence(tmp_path: Path) -> None:
    from minicc.session import SessionError, SessionStore, missing_session_message

    session = SessionStore(tmp_path, "missing")
    with pytest.raises(SessionError) as excinfo:
        session.fork(1)
    assert str(excinfo.value) == missing_session_message("missing.json")


def test_the_rewind_gate_raises_the_homes_sentence(tmp_path: Path) -> None:
    from minicc.session import SessionError, SessionStore, missing_session_message

    session = SessionStore(tmp_path, "missing")
    with pytest.raises(SessionError) as excinfo:
        session.rewind(1)
    assert str(excinfo.value) == missing_session_message("missing.json")


def test_the_rewind_to_user_gate_raises_the_homes_sentence(tmp_path: Path) -> None:
    from minicc.session import SessionError, SessionStore, missing_session_message

    session = SessionStore(tmp_path, "missing")
    with pytest.raises(SessionError) as excinfo:
        session.rewind_to_user_index(1)
    assert str(excinfo.value) == missing_session_message("missing.json")
