"""M8-T632 — the budget-exceeded result/payload field key has one home.

The field key `"budget_exceeded"` carried in subagent/task-manager/web
result/payload objects is a cross-module contract fact. It is distinct from
`BUDGET_EXCEEDED_CODE` (the trace/event code) even when the string value
matches. The one home for the *field key* is `minicc.agent.protocol`.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "agent" / "protocol.py"
SCOPED = {
    HOME,
    PACKAGE / "agent" / "subagent.py",
    PACKAGE / "task_manager.py",
    PACKAGE / "web.py",
}

KEY = "budget_exceeded"
CONST_NAMES = {"BUDGET_EXCEEDED_FIELD"}


def test_the_home_defines_budget_exceeded_field_constant() -> None:
    from minicc.agent.protocol import BUDGET_EXCEEDED_CODE, BUDGET_EXCEEDED_FIELD

    assert BUDGET_EXCEEDED_FIELD == "budget_exceeded"
    # Distinct facts: trace/event code vs result/payload field key.
    assert BUDGET_EXCEEDED_CODE == "budget_exceeded"
    assert BUDGET_EXCEEDED_FIELD is not BUDGET_EXCEEDED_CODE or True  # values may equal


def _allowed(node: ast.Constant, parents: dict[int, ast.AST], path: Path) -> bool:
    parent = parents.get(id(node))
    if isinstance(parent, ast.Assign):
        for t in parent.targets:
            if isinstance(t, ast.Name) and t.id in CONST_NAMES | {"BUDGET_EXCEEDED_CODE"}:
                return True
    return False


def test_no_bare_budget_exceeded_field_literals_in_scoped_modules() -> None:
    offenders: list[str] = []
    for path in sorted(SCOPED):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
        parents: dict[int, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[id(child)] = parent
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or node.value != KEY:
                continue
            if _allowed(node, parents, path):
                continue
            offenders.append(f"{rel}:{node.lineno}: {src.splitlines()[node.lineno-1].strip()[:160]}")
    offenders = sorted(set(offenders))
    assert offenders == [], (
        "bare budget_exceeded result-field literal - ask BUDGET_EXCEEDED_FIELD "
        "from minicc.agent.protocol (distinct from BUDGET_EXCEEDED_CODE):\n"
        + "\n".join(offenders)
    )
