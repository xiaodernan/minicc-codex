"""M8-T430 — 会话清单载荷三键两个家：RPC 方法与服务面列表各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/web.py"

FIELDS = {"count", "sessions", "workspace_path"}


def test_the_home_builds_the_listing() -> None:
    """The constructor owns the three keys; count is derived, never passed."""
    from minicc.web import _sessions_payload

    payload = _sessions_payload("/ws", [{"id": "a"}, {"id": "b"}])
    assert payload == {
        "workspace_path": "/ws",
        "count": 2,
        "sessions": [{"id": "a"}, {"id": "b"}],
    }
    assert _sessions_payload("/ws", [])["count"] == 0


def test_the_three_keys_are_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second listing shape."""
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
        "the sessions listing is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )


def test_both_listings_ask_the_home() -> None:
    """The RPC method, the service lister, and the definition itself."""
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("_sessions_payload(") == 3, (
        "the definition plus the two listings are the only spellings, "
        f"found {source.count('_sessions_payload(')}"
    )
