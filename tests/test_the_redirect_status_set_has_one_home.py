"""M8-T579 — the 5-status redirect set has one home.

``301, 302, 303, 307, 308`` — the statuses that carry a Location and may be
followed as a redirect — were hand-spelled in four places across two files:
``minicc/tools/webfetch.py`` (three times) and ``minicc/mcp.py`` (once).
Both HTTP clients that permit redirects special-case exactly that set; a
status added to or removed from the home (``minicc/netguard.py``,
``REDIRECT_STATUSES``) had no way to propagate, and the next redirect-capable
client would have started a fifth spelling.

This gate pins the consolidation:

* ``minicc/netguard.py`` defines ``REDIRECT_STATUSES`` as exactly the five
  codes (M8-T491's redirect-limit verdict already lives there; the set is
  the same fact about the same two clients), and
* no other file under ``minicc/`` spells any container (set, tuple, list,
  or ``frozenset({...})``) holding three or more of the five codes.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "netguard.py"
CODES = {301, 302, 303, 307, 308}


def _containers(tree: ast.Module):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Set, ast.Tuple, ast.List)):
            yield node, node.elts
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "frozenset"
            and node.args
            and isinstance(node.args[0], ast.Set)
        ):
            yield node, node.args[0].elts


def test_netguard_defines_exactly_the_five_redirect_codes() -> None:
    tree = ast.parse(HOME.read_text(encoding="utf-8"), filename=str(HOME))
    found = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "REDIRECT_STATUSES" for t in node.targets
        ):
            value = node.value
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "frozenset"
                and value.args
                and isinstance(value.args[0], ast.Set)
            ):
                elts = value.args[0].elts
            elif isinstance(value, ast.Set):
                elts = value.elts
            else:
                elts = ()
            found = {
                elt.value
                for elt in elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, int)
            }
    assert found == CODES, (
        f"minicc/netguard.py must define REDIRECT_STATUSES as exactly {sorted(CODES)} "
        f"(got {found})"
    )


def test_no_other_module_spells_the_redirect_status_set() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if path.resolve() == HOME.resolve():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node, elts in _containers(tree):
            values = {
                elt.value
                for elt in elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, int)
            }
            shared = CODES & values
            if len(shared) >= 3:
                offenders.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}: {sorted(shared)}")
    assert offenders == [], (
        "these containers re-spell the redirect statuses (import "
        "REDIRECT_STATUSES from minicc/netguard.py instead): "
        f"{offenders}"
    )
