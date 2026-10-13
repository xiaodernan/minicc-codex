"""Shared census + reason-detection for the silence gates (M8-T190, M8-T230).

Two gates decide whether a broad ``except`` handler is allowed to swallow an
exception: the pass/continue/break family (``test_silence_must_state_its_reason.py``)
and the bare-return family (``test_broad_except_return_swallows_state_reason.py``).
They must agree on (a) how ``minicc/`` is walked and (b) what counts as "a stated
reason", so that logic lives here once instead of being copied into each gate.

A reason is stated in either of two spellings:
  * a ``noqa`` marker on the ``except`` line, or
  * a comment between the ``except`` line and the first statement of its body.

AST keeps no comment nodes, so the comment form is read off the source lines.
"""
from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCE_DIR = REPO / "minicc"
BROAD_TYPES = frozenset({"Exception", "BaseException"})


def stated_reason(lines: list[str], node: ast.ExceptHandler) -> str:
    """Why is this handler allowed to swallow? Empty string means it never said."""
    first_body = min(stmt.lineno for stmt in node.body)
    for line in lines[node.lineno:first_body - 1]:
        stripped = line.strip()
        if stripped.startswith("#") and stripped != "#":
            return stripped.lstrip("#").strip()
    return "noqa" if "noqa" in lines[node.lineno - 1] else ""


def _site(path: Path, source_dir: Path) -> str:
    """Where the handler lives, for a message someone can act on.

    Both gates walk the shipped tree, so the repo-relative spelling is what they
    print. A mutation cell walks a temporary tree instead - see M8-T239, which is
    why the fallback exists: pointing the census at a fixture tree is what lets a
    cell prove the detector notices a bare silence without editing the repo.
    """
    for base in (REPO, source_dir):
        try:
            return path.relative_to(base).as_posix()
        except ValueError:
            continue
    return path.name


def census_silent(
    predicate: Callable[[ast.ExceptHandler], bool],
    source_dir: Path = SOURCE_DIR,
) -> list[tuple[str, str]]:
    """``(site, reason)`` for every broad handler whose body matches ``predicate``."""
    found: list[tuple[str, str]] = []
    for path in sorted(p for p in source_dir.rglob("*.py") if "__pycache__" not in p.parts):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.ExceptHandler) and predicate(node):
                found.append((f"{_site(path, source_dir)}:{node.lineno}",
                              stated_reason(lines, node)))
    return found
