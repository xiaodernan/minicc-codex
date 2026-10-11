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
                found.append((f"{path.relative_to(REPO).as_posix()}:{node.lineno}",
                              stated_reason(lines, node)))
    return found
