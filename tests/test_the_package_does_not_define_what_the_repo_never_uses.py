"""M8-T578 — the package does not define what the repository never uses.

A single-line constant in the task manager survived months with nothing in
the module using it, no test importing it, no handler reading it — only a
dead re-export in two other modules and nothing else, across the whole
repository including docs.  A reader who trusts the module's constants to
mean something is misled; a sweeper who only looks at imports (M8-T575's
gate) misses this class entirely.

This gate sweeps the repository once and pins one rule:

* every module-scope name assigned in ``minicc/`` that is constant-shaped
  (``UPPER_SNAKE`` or ``_private``) and not declared in its own module's
  ``__all__`` must be referenced somewhere as a real ``Name`` occurrence —
  or appear inside any string constant.  Import aliases do not count: an
  import that only re-exports and is never consumed is dead twice (the
  dead-import gate would not see it behind ``# noqa: F401 - re-export``, so
  this gate is the net for that shape).

Star imports do not exist in this repository today; if one ever appears, a
constant-only-consumed-that-way belongs in its module's ``__all__`` or the
name will be reported.  Comments do not count as references.
"""

from __future__ import annotations

import ast
import pathlib
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = [REPO / "minicc", REPO / "tests", REPO / "scripts", REPO]
SUFFIX = ".py"


def _all_py_files() -> list[pathlib.Path]:
    seen: set[pathlib.Path] = set()
    files: list[pathlib.Path] = []
    for root in SOURCE_ROOTS:
        iterable = [root] if root.is_file() else root.rglob(f"*{SUFFIX}")
        for path in iterable:
            if not path.is_file():
                continue
            if any(part in ("node_modules", "build", ".git") for part in path.parts):
                continue
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                files.append(path)
    return sorted(files)


def _module_all(tree: ast.Module) -> set[str]:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__all__":
                if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                    return {
                        element.value
                        for element in node.value.elts
                        if isinstance(element, ast.Constant)
                        and isinstance(element.value, str)
                    }
    return set()


def _definition_target_ids(tree: ast.Module) -> set[int]:
    ids: set[int] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            _collect_name_node_ids(target, ids)
    return ids


def _collect_name_node_ids(node, out: set[int]) -> None:
    if isinstance(node, ast.Name):
        out.add(id(node))
    elif isinstance(node, (ast.Tuple, ast.List)):
        for element in node.elts:
            _collect_name_node_ids(element, out)
    elif isinstance(node, ast.Starred):
        _collect_name_node_ids(node.value, out)


def test_no_constant_is_defined_without_any_repository_reference() -> None:
    files = _all_py_files()
    parsed: dict[pathlib.Path, tuple[ast.Module, set[int]]] = {}
    referenced: set[str] = set()
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        def_ids = _definition_target_ids(tree)
        parsed[path] = (tree, def_ids)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                if id(node) not in def_ids:
                    referenced.add(node.id)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                referenced.update(_identifier_tokens(node.value))

    offenders: list[str] = []
    for path, (tree, _def_ids) in sorted(parsed.items()):
        relative = path.relative_to(REPO).as_posix()
        if not (relative == "minicc" or relative.startswith("minicc/")):
            continue
        exported = _module_all(tree)
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                for name in _flattened_target_names(target):
                    if name.startswith("__"):
                        continue
                    if name in exported:
                        continue
                    if not _constant_shaped(name):
                        continue
                    if name not in referenced:
                        offenders.append(f"{relative}:{node.lineno}: {name}")
    assert offenders == [], (
        "these module-scope constants are referenced nowhere in the "
        "repository - not by code, imports, or any string (delete them, or "
        f"declare them in the module's __all__ if they are public API): {offenders}"
    )


def _constant_shaped(name: str) -> bool:
    if name.startswith("_"):
        return True
    return all(c.isupper() or c.isdigit() or c == "_" for c in name)


def _identifier_tokens(text: str) -> set[str]:
    return set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text))


def _flattened_target_names(target) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        out: list[str] = []
        for element in target.elts:
            out.extend(_flattened_target_names(element))
        return out
    return []
