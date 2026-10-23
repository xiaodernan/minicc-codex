"""M8-T439 — 空会话兜底载荷两键两个家：文件不存在与解析失败各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/session.py"

FIELDS = {"messages", "version"}


def test_the_home_builds_the_fallback() -> None:
    """The constructor owns the pair and stamps the format version."""
    from minicc.session import SESSION_FORMAT_VERSION, _empty_payload

    payload = _empty_payload()
    assert payload == {"version": SESSION_FORMAT_VERSION, "messages": []}


def test_the_two_keys_are_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second fallback shape."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = {
                key.value
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            if keys == FIELDS:
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the empty-session fallback is spelled by hand outside its one "
        "home: " + ", ".join(offenders)
    )


def test_both_fallbacks_ask_the_home() -> None:
    """The missing-file branch, the bad-parse branch, and the definition."""
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("_empty_payload(") == 3, (
        "the definition plus the two fallbacks are the only spellings, "
        f"found {source.count('_empty_payload(')}"
    )
