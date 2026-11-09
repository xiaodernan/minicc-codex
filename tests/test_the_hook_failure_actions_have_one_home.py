"""M8-T680 — hook failure actions have one home.

``HOOK_FAILURE_CONTINUE`` / ``HOOK_DECISION_DENY`` (via ``HOOK_FAILURE_ACTIONS``)
in ``minicc/hooks.py`` are the hook's failure-action vocabulary.  The doc
example in the module docstring keeps the literals (it is user-facing JSON
readme); everything else in the module goes through the constants.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOME = REPO / "minicc" / "hooks.py"
VALUE = "continue"
DEF_NAME = "HOOK_FAILURE_CONTINUE"


def _prose_nodes(tree: ast.Module) -> set[int]:
    prose: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            for child in ast.walk(node):
                prose.add(id(child))
    return prose


def test_the_home_defines_the_failure_actions() -> None:
    import minicc.hooks as hooks

    assert hooks.HOOK_FAILURE_CONTINUE == "continue"
    assert hooks.HOOK_DECISION_DENY == "deny"
    assert hooks.HOOK_FAILURE_ACTIONS == frozenset({"continue", "deny"})


def test_no_bare_continue_literal_remains_outside_the_definition() -> None:
    src = HOME.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(HOME))
    prose = _prose_nodes(tree)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or node.value != VALUE:
            continue
        if id(node) in prose:
            continue
        line = src.splitlines()[node.lineno - 1]
        if line.startswith("HOOK_FAILURE_CONTINUE"):
            continue
        offenders.append(f"{HOME.name}:{node.lineno}: {line.strip()[:170]}")
    assert offenders == [], (
        "bare hook failure-action literal - use HOOK_FAILURE_CONTINUE "
        "from minicc.hooks:\n" + "\n".join(offenders)
    )
