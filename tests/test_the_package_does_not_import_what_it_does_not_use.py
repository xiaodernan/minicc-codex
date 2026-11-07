"""M8-T575 — the package carries no dead module-scope imports.

``minicc/web.py`` had 33 imports nothing references, and the census that
found them also found a dozen more across the package (``bench_tasks.py``
imports ``time`` and never calls it; ``webserver.py`` imports ``Path``
likewise; ``audit.py`` imports ``match_permission_rule`` and never reaches
it).  A reader opening a module should be able to trust three facts about
its imports:

* what the module imports is what the module is about;
* if an import is absent the module does not depend on it;
* an import that is only a re-export says so, and stays.

This gate sweeps every ``.py`` under ``minicc/`` with an AST, skipping:

* ``__future__`` markers — behaviour hints, not names;
* lines marked ``# noqa: F401`` or commented ``re-export`` — declared public
  surface of the package; and
* names listed in the module's own ``__all__`` — explicit re-exports.

Everything else must be referenced in the same module.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"


def _load(path: Path) -> tuple[ast.Module, list[str]]:
    text = path.read_text(encoding="utf-8")
    return ast.parse(text, filename=str(path)), text.splitlines()


def test_no_module_scope_import_is_unreferenced() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        tree, lines = _load(path)
        used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        exported = _explicit_exports(tree)
        for node in tree.body:
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            segment = "\n".join(lines[node.lineno - 1:node.end_lineno]).lower()
            if (
                (isinstance(node, ast.ImportFrom) and node.module == "__future__")
                or "# noqa: f401" in segment
                or "# re-export" in segment
            ):
                continue
            if isinstance(node, ast.Import):
                bound = [alias.asname or alias.name.split(".")[0] for alias in node.names]
            else:
                bound = [
                    alias.asname or alias.name
                    for alias in node.names
                    if alias.name != "*"
                ]
            for name in bound:
                if name in used or name in exported:
                    continue
                relative = path.relative_to(REPO).as_posix()
                offenders.append(f"{relative}:{node.lineno}: {name}")
    assert offenders == [], (
        "these module-scope imports are never referenced and not declared "
        "as re-exports (delete them, or add a # noqa: F401 if they are for "
        f"someone else): {offenders}"
    )


def _explicit_exports(tree: ast.Module) -> set[str]:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names: set[str] = set()
        for target in node.targets:
            names.update(name.id for name in _flattened_names(target))
        if "__all__" not in names:
            continue
        if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
            return {
                element.value
                for element in node.value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            }
    return set()


def _flattened_names(target) -> list[ast.Name]:
    out: list[ast.Name] = []
    if isinstance(target, ast.Name):
        out.append(target)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for element in target.elts:
            out.extend(_flattened_names(element))
    return out
