"""M8-T596 — the tree ceilings live only in the tool declaration.

``fs.py``'s ``tree`` handler reads no clamp: it trusts the tool schema to
bound ``max_depth``/``max_entries`` (fs.py documents this in a comment —
"max_depth <= 8, max_entries <= 2000. They are enforced there"). The two
ceilings therefore exist exactly once, as Param literals in
``tools/__init__.py``.

A previous edit glued ``depth_p.max_value`` to ``web.MAX_RESULTS`` — the
web-search results cap. Same number (8), different fact: the tree ceiling is
the tool boundary's own. This gate pins the declaration side of that fact:

* ``depth_p.max_value`` is the int literal 8 and nothing else;
* ``entries_p.max_value`` is the int literal 2000;
* neither references another vocabulary's constant by name.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOLS_INIT = REPO / "minicc" / "tools" / "__init__.py"


def _params(tree: ast.Module):
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)):
            continue
        value = node.value
        if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "Param"):
            continue
        yield node.targets[0].id, {kw.arg: kw.value for kw in value.keywords}


def test_the_tree_ceilings_are_the_tool_boundary_literals() -> None:
    tree = ast.parse(TOOLS_INIT.read_text(encoding="utf-8"), filename=str(TOOLS_INIT))
    params = dict(_params(tree))
    for name, expected in (("depth_p", 8), ("entries_p", 2000)):
        node = params.get(name)
        assert node is not None, f"{name} Param declaration not found"
        max_node = node.get("max_value")
        assert isinstance(max_node, ast.Constant) and max_node.value == expected, (
            f"{name}.max_value must be the tool boundary's own literal {expected} - "
            "not a name reaching into another vocabulary (it is not the web-search results cap)"
        )
