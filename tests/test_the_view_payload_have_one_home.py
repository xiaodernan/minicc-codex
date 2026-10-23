"""M8-T416 — 会话视图载荷形状两个家：模块级默认常量与归一器返回字面量"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/session.py"

FIELDS = {"version", "last_item", "last_tool", "compact_tools", "tool_history"}


def test_the_home_builds_the_payload() -> None:
    """The constructor owns the five keys and their defaults."""
    from minicc.session import _view_payload

    payload = _view_payload()
    assert payload == {
        "version": 1, "last_item": 0, "last_tool": 0,
        "compact_tools": True, "tool_history": [],
    }
    assert _view_payload(last_item=7, last_tool=2, compact_tools=False)["last_item"] == 7


def test_every_read_takes_a_fresh_payload() -> None:
    """No shared inner list: the old ``dict(_DEFAULT_VIEW)`` shared one."""
    from minicc.session import SessionStore, _view_payload

    first, second = _view_payload(), _view_payload()
    assert first["tool_history"] is not second["tool_history"]
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert "_DEFAULT_VIEW" not in source.replace(
        "``dict(_DEFAULT_VIEW)`` call sites", ""
    ), "the shared default constant must not come back"


def test_the_normalizer_still_fills_every_field(tmp_path: Path) -> None:
    """Behavior unchanged: a stored view is normalized, not trusted."""
    from minicc.session import SessionStore

    store = SessionStore(tmp_path / "sess")
    normalized = store.load_view_payload({
        "last_item": "7", "last_tool": -3, "compact_tools": 0,
        "tool_history": [{"index": 1, "tool": "bash", "summary": "x"}],
    })
    assert normalized == {
        "version": 1, "last_item": 7, "last_tool": 0, "compact_tools": False,
        "tool_history": [{"index": "1", "tool": "bash", "summary": "x"}],
    }, normalized


def test_the_payload_is_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second view shape."""
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
        "the view payload shape is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )
