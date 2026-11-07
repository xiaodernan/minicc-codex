"""M8-T574 — the web module carries no dead imports.

``minicc/web.py`` had accumulated seventeen module-scope imports that named
nothing ever used — vestigial scaffolding from an earlier shape of the file,
plus a couple that only appeared in its docstring examples.  A reader who
looks at the import list to learn what the module needs and finds names that
signify nothing ends up reading random identifiers like ``urlsplit`` against
a codebase that never uses them.

This gate pins exactly the rule that would have caught those:

* for every import at module scope in ``minicc/web.py``,
* unless the import is marked ``# noqa: F401`` or the name appears in a
  re-export comment (the module deliberately re-exports it for consumers and
  tests),
* the imported name must appear somewhere in the module's AST.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "minicc" / "web.py"


def _load() -> ast.Module:
    return ast.parse(SOURCE.read_text(encoding="utf-8"))


def _names_referenced(tree: ast.Module) -> set[str]:
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}


def test_no_module_scope_import_is_unreferenced() -> None:
    tree = _load()
    used = _names_referenced(tree)
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    offenders: list[str] = []
    for node in tree.body:
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        segment = "\n".join(lines[node.lineno - 1:node.end_lineno])
        normalized = segment.lower()
        if "# noqa: f401" in normalized:
            continue
        if "# re-export" in normalized:
            continue
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            # ``from __future__ import annotations`` is a behaviour marker, not
            # a value anyone references by name.
            continue
        if isinstance(node, ast.Import):
            bound = [alias.asname or alias.name.split(".")[0] for alias in node.names]
        else:
            bound = [alias.asname or alias.name for alias in node.names if alias.name != "*"]
        for name in bound:
            if name not in used:
                offenders.append(f"{node.lineno}: {name}")
    assert offenders == [], (
        "minicc/web.py imports these module-scope names but never references "
        f"them (no Name use anywhere in the module): {offenders}"
    )
