"""M8-T432 — 审计导出载荷四键两个家：空导出与截断页各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/web.py"

FIELDS = {"count", "entries", "total", "workspace_path"}


def test_the_home_builds_the_page() -> None:
    """count is derived from the page; total counts every match."""
    from minicc.web import _audit_export_payload

    page = _audit_export_payload("/ws", [{"a": 1}, {"a": 2}], 9)
    assert page == {
        "workspace_path": "/ws",
        "entries": [{"a": 1}, {"a": 2}],
        "count": 2,
        "total": 9,
    }
    assert _audit_export_payload("/ws", [], 0) == {
        "workspace_path": "/ws",
        "entries": [],
        "count": 0,
        "total": 0,
    }


def test_the_four_keys_are_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second page shape."""
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
        "the audit export page is spelled by hand outside its one "
        "home: " + ", ".join(offenders)
    )


def test_both_exports_ask_the_home() -> None:
    """The empty export, the capped page, and the definition itself."""
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("_audit_export_payload(") == 3, (
        "the definition plus the two exports are the only spellings, "
        f"found {source.count('_audit_export_payload(')}"
    )
