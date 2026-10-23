"""M8-T436 — MCP 缺席状态两键两个家：workspace_info 与 /api/mcp 各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/mcp.py"

FIELDS = {"configured", "error"}


def test_the_home_builds_the_absent_status() -> None:
    """The constructor owns the two keys; configured is structurally zero."""
    from minicc.mcp import mcp_absent_status

    assert mcp_absent_status("no config") == {"configured": 0, "error": "no config"}


def test_the_two_keys_are_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second fallback shape.

    The healthy ``status()`` payload is four keys (``servers`` and
    friends), so it cannot collide with this census.
    """
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
        "the MCP-absent status is spelled by hand outside its one "
        "home: " + ", ".join(offenders)
    )


def test_both_surfaces_ask_the_home() -> None:
    """The workspace-info fallback, the route fallback, and the definition."""
    for site in ("minicc/web.py", "minicc/webserver.py"):
        source = (REPO / site).read_text(encoding="utf-8")
        assert source.count("mcp_absent_status(") == 1, (
            f"{site} must call the home exactly once, found "
            f"{source.count('mcp_absent_status(')}"
        )
