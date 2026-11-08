"""M8-T652 — task result `children_rolled_up` payload field name has one home.

Home is `minicc.task_contract.RESULT_FIELD_CHILDREN_ROLLED_UP`. Scoped to
`task_contract` and `task_execution` (same incremental contract-fact pattern
as RESULT_FIELD_TOKENS_USED/ANSWER/ERROR).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCOPED = {REPO / "minicc" / "task_contract.py", REPO / "minicc" / "task_execution.py"}
VAL = "children_rolled_up"
DEF_NAME = "RESULT_FIELD_CHILDREN_ROLLED_UP"


def test_the_home_defines_result_field_children_rolled_up() -> None:
    from minicc.task_contract import RESULT_FIELD_CHILDREN_ROLLED_UP

    assert RESULT_FIELD_CHILDREN_ROLLED_UP == "children_rolled_up"


def test_no_bare_children_rolled_up_field_literals_in_scoped_modules() -> None:
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
            if isinstance(parent, ast.Assign):
                if any(isinstance(t, ast.Name) and t.id == DEF_NAME for t in parent.targets):
                    continue
            offenders.append(f"{rel}:{node.lineno}: {src.splitlines()[node.lineno-1].strip()[:160]}")
    offenders = sorted(set(offenders))
    assert offenders == [], (
        "bare task-result children_rolled_up field literal - use "
        "RESULT_FIELD_CHILDREN_ROLLED_UP from minicc.task_contract:\n" + "\n".join(offenders)
    )
