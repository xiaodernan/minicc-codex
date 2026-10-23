"""M8-T395 — 协议前缀元组两个家：mcp.py 与 tools/web.py 各写一份 startswith Tuple"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/netguard.py"

PREFIXES = frozenset({"http://", "https://"})


def test_the_home_exists_in_netguard() -> None:
    """netguard.py owns the wire form, derived from ALLOWED_SCHEMES."""
    from minicc.netguard import ALLOWED_SCHEMES, SCHEME_PREFIXES

    assert SCHEME_PREFIXES == tuple(
        f"{scheme}://" for scheme in sorted(ALLOWED_SCHEMES)
    )
    assert set(SCHEME_PREFIXES) == PREFIXES


def test_both_consumers_import_the_same_object() -> None:
    """mcp.py and tools/web.py ask the home, not a copy of it."""
    from minicc import mcp, netguard
    from minicc.tools import web

    assert mcp.SCHEME_PREFIXES is netguard.SCHEME_PREFIXES
    assert web.SCHEME_PREFIXES is netguard.SCHEME_PREFIXES


def test_no_module_inlines_the_prefixes() -> None:
    """No module spells the prefix tuple as a literal outside the one declaration."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Set | ast.Tuple | ast.List):
                continue
            elements = frozenset(
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
            if len(node.elts) >= 2 and elements == PREFIXES:
                offenders.append(f"{relative}:{node.lineno}")
    assert not offenders, (
        "the scheme prefixes are spelled inline instead of derived from "
        "ALLOWED_SCHEMES in " + HOME + ": " + ", ".join(offenders)
    )


def test_the_prefixes_still_gate_the_wire_forms() -> None:
    """startswith with the home accepts http/https URLs and rejects the rest."""
    from minicc.netguard import SCHEME_PREFIXES

    assert "http://example.test".startswith(SCHEME_PREFIXES)
    assert "https://example.test".startswith(SCHEME_PREFIXES)
    assert not "ftp://example.test".startswith(SCHEME_PREFIXES)
    assert not "file:///etc/passwd".startswith(SCHEME_PREFIXES)
