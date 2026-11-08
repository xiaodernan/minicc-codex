"""M8-T642 — task result `cancelled` payload field name has one home.

The result-contract field name `"cancelled"` is shared by `minicc.task_contract`
and `minicc.task_execution`. Home is `minicc.task_contract.RESULT_FIELD_CANCELLED`.
Distinct from `TASK_STATUS_CANCELLED` (status value fact).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCOPED = {
    REPO / "minicc" / "task_contract.py",
    REPO / "minicc" / "task_execution.py",
    REPO / "minicc" / "task_worker.py",
}
HOME = REPO / "minicc" / "task_contract.py"
VAL = "cancelled"
DEF_NAME = "RESULT_FIELD_CANCELLED"


def test_the_home_defines_result_field_cancelled() -> None:
    from minicc.task_contract import RESULT_FIELD_CANCELLED

    assert RESULT_FIELD_CANCELLED == "cancelled"


def test_no_bare_cancelled_field_literals_in_scoped_modules() -> None:
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
            if not isinstance(node, ast.Constant) or node.value != VAL:
                continue
            parent = parents.get(id(node))
            if path == HOME and isinstance(parent, ast.Assign):
                if any(isinstance(t, ast.Name) and t.id == DEF_NAME for t in parent.targets):
                    continue
            offenders.append(f"{rel}:{node.lineno}: {src.splitlines()[node.lineno-1].strip()[:160]}")
    offenders = sorted(set(offenders))
    assert offenders == [], (
        "bare task-result cancelled field literal - use RESULT_FIELD_CANCELLED "
        "from minicc.task_contract (distinct from TASK_STATUS_CANCELLED):\n"
        + "\n".join(offenders)
    )
