"""The exemption for pytest's own scandir leak must not be able to hide ours.

``conftest._skip_upstream_scandir_sweep`` stops pytest's session-end GC sweep
because ``_pytest.pathlib.find_prefixed()`` abandons an ``os.scandir()``
iterator and the resulting ``ResourceWarning`` was failing green runs under
``-W error``. An exemption like that is only honest if our own code *cannot*
produce the thing being exempted - otherwise it would swallow a real leak with
the same message. Two claims make that argument checkable instead of asserted:

1. ``minicc/`` and ``scripts/`` never call ``os.scandir`` - the only API that
   raises "unclosed scandir iterator" directly.
2. Every ``Path.iterdir()`` call is consumed inside the same expression, so the
   ``os.scandir`` iterator it wraps cannot outlive that expression. An abandoned
   ``iterdir()`` generator produces the identical warning, so this is the second
   half of the same hole.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIRS = (REPO_ROOT / "minicc", REPO_ROOT / "scripts")

#: Anti-vacuity floor: the walker must find the iterdir() sites that exist
#: today. If a refactor renames the pattern, this gate fails loudly instead of
#: passing because it found nothing to check.
_MIN_ITERDIR_SITES = 4

#: Calls that consume an iterator in the same expression.
_CONSUMERS = {"list", "sorted", "set", "tuple", "frozenset", "any", "all", "sum", "max", "min"}


def _sources() -> list[Path]:
    files: list[Path] = []
    for directory in PACKAGE_DIRS:
        files.extend(sorted(path for path in directory.rglob("*.py") if "__pycache__" not in path.parts))
    return files


def _scandir_calls(tree: ast.AST) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "scandir":
            lines.append(node.lineno)
    return lines


def _iterdir_calls(tree: ast.AST) -> list[int]:
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "iterdir"
    ]


def _consumed_iterdir_lines(tree: ast.AST) -> set[int]:
    """Lines where an iterdir() call is consumed by its enclosing expression."""
    consumed: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.comprehension)):
            for child in ast.walk(node.iter):
                if (
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and child.func.attr == "iterdir"
                ):
                    consumed.add(child.lineno)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _CONSUMERS:
            for child in ast.walk(node):
                if (
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and child.func.attr == "iterdir"
                ):
                    consumed.add(child.lineno)
    return consumed


def test_project_code_never_opens_a_scandir_iterator() -> None:
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{line}"
        for path in _sources()
        for line in _scandir_calls(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert offenders == [], (
        "os.scandir must be used as a context manager (or not at all): the "
        "session-end sweep that reports abandoned scandir iterators is exempted "
        "for pytest's own leak, so an unclosed one here would be swallowed. "
        f"Offenders: {offenders}"
    )


def test_every_iterdir_call_is_consumed_in_the_same_expression() -> None:
    sites: list[tuple[str, int]] = []
    abandoned: list[str] = []
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        consumed = _consumed_iterdir_lines(tree)
        for line in _iterdir_calls(tree):
            sites.append((str(path.relative_to(REPO_ROOT)), line))
            if line not in consumed:
                abandoned.append(f"{path.relative_to(REPO_ROOT)}:{line}")
    assert len(sites) >= _MIN_ITERDIR_SITES, (
        f"only {len(sites)} iterdir() site(s) found; the walker is looking at the "
        f"wrong shape, not at a clean tree. Sites: {sites}"
    )
    assert abandoned == [], (
        "iterdir() returns a generator over os.scandir; assigning it and not "
        "consuming it to exhaustion leaves the iterator to the GC, which is the "
        "same unraisable the exemption above covers. Consume it in one "
        f"expression (for/comprehension/list()/sorted()): {abandoned}"
    )
