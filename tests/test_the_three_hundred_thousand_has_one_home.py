"""M8-T584 — the 300k default context budget has one home.

``300_000`` is the default answer to "how big is the window?" and "when
does compaction trigger?".  ``minicc/config.py`` defines both
``DEFAULT_CONTEXT_WINDOW_TOKENS`` and ``DEFAULT_COMPACT_THRESHOLD`` for it;
call sites that wrote the bare literal instead of asking the homes silently
kept working, but the two knobs could not ever diverge — and nobody could
find every definition to change one without the other.

This gate pins: no file under ``minicc/`` other than ``minicc/config.py``
spells the integer literal ``300000`` (underscored or not, any base-10
spelling).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "config.py"
FORBIDDEN = 300_000


def test_no_bare_three_hundred_thousand_outside_config() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if path.resolve() == HOME.resolve():
            continue
        relative = path.relative_to(REPO).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, int) and node.value == FORBIDDEN:
                offenders.append(f"{relative}:{node.lineno}")
    assert offenders == [], (
        "the 300_000 default context budget is spelled outside its homes "
        "(DEFAULT_CONTEXT_WINDOW_TOKENS / DEFAULT_COMPACT_THRESHOLD in "
        f"minicc/config.py - import those instead): {offenders}"
    )


def test_config_defines_the_two_homes_with_the_shared_value() -> None:
    from minicc.config import DEFAULT_COMPACT_THRESHOLD, DEFAULT_CONTEXT_WINDOW_TOKENS

    assert DEFAULT_COMPACT_THRESHOLD == FORBIDDEN
    assert DEFAULT_CONTEXT_WINDOW_TOKENS == FORBIDDEN
