"""M8-T381 — ALLOWED_SCHEMES 一个键三个家：netguard/webfetch/webauth"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"


def test_the_allowed_schemes_exist_in_netguard() -> None:
    """ALLOWED_SCHEMES exists in netguard.py."""
    from minicc.netguard import ALLOWED_SCHEMES
    assert ALLOWED_SCHEMES == frozenset({"http", "https"})


def test_webfetch_and_webauth_import_from_netguard() -> None:
    """webfetch.py and webauth.py import ALLOWED_SCHEMES from netguard."""
    from minicc.tools.webfetch import ALLOWED_SCHEMES as WeFetchSchemes
    from minicc.webauth import ALLOWED_SCHEMES as WebAuthSchemes

    assert WeFetchSchemes == frozenset({"http", "https"})
    assert WebAuthSchemes == frozenset({"http", "https"})

    # Verify they are the same value (structural assertion)
    assert str(WeFetchSchemes) == str(WebAuthSchemes)


def test_no_module_has_inline_http_https_set() -> None:
    """No module in the package hard-codes {"http", "https"} inline (outside netguard)."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Set):
                continue
            # Check if this is exactly {"http", "https"}
            elements = frozenset(
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
            if elements == frozenset({"http", "https"}) and len(node.elts) == 2:
                relative = path.relative_to(REPO).as_posix()
                # Allow netguard.py since that's the home
                if relative != "minicc/netguard.py":
                    offenders.append(f"{relative}:{node.lineno}")
    assert not offenders, (
        "Inline \"http\", \"https\" sets found outside "
        "their one home (minicc/netguard.py): "
        + ", ".join(offenders)
    )


def test_the_home_is_in_netguard_py() -> None:
    """The home is in netguard.py and is exported."""
    import minicc.netguard as ng

    assert hasattr(ng, "ALLOWED_SCHEMES"), "netguard must export ALLOWED_SCHEMES"
    assert ng.ALLOWED_SCHEMES == frozenset({"http", "https"})