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


def test_webauth_imports_the_scheme_vocabulary_from_netguard() -> None:
    """webauth.py judges CORS origins, so it reads ALLOWED_SCHEMES directly."""
    from minicc.webauth import ALLOWED_SCHEMES as WebAuthSchemes

    assert WebAuthSchemes == frozenset({"http", "https"})


def test_webfetch_reads_the_pre_flight_that_owns_the_scheme_gate() -> None:
    """M8-T475: webfetch no longer spells the scheme gate itself.

    It used to import ``ALLOWED_SCHEMES`` and re-run the scheme and
    hostname checks with its own copy of both sentences.  It now calls
    ``netguard.parse_http_url``, which owns those two checks - so the
    vocabulary is still read from one home, one level further out.  This
    gate had to learn the new shape, exactly as T473 taught: a census that
    pins the *old* indirection pushes the next reader to undo the fix.
    """
    import minicc.netguard as netguard
    from minicc.tools.webfetch import parse_http_url as webfetch_pre_flight

    assert webfetch_pre_flight is netguard.parse_http_url


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