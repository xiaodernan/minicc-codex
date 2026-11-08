"""M8-T648 — task result `answer`/`error` payload field names have one home.

Home is `minicc.task_contract`. Scoped to `task_contract` and `task_execution`.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCOPED = {REPO / "minicc" / "task_contract.py", REPO / "minicc" / "task_execution.py"}
VALS = {"answer": "RESULT_FIELD_ANSWER", "error": "RESULT_FIELD_ERROR"}


def test_the_home_defines_answer_error_field_constants() -> None:
    from minicc.task_contract import RESULT_FIELD_ANSWER, RESULT_FIELD_ERROR

    assert RESULT_FIELD_ANSWER == "answer"
    assert RESULT_FIELD_ERROR == "error"


def test_no_bare_answer_error_field_literals_in_scoped_modules() -> None:
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
            if not isinstance(node, ast.Constant) or node.value not in VALS:
                continue
            parent = parents.get(id(node))
            if isinstance(parent, ast.Assign):
                if any(isinstance(t, ast.Name) and t.id == VALS[node.value] for t in parent.targets):
                    continue
            offenders.append(f"{rel}:{node.lineno}: {src.splitlines()[node.lineno-1].strip()[:160]}")
    offenders = sorted(set(offenders))
    assert offenders == [], (
        "bare task-result answer/error field literal - use RESULT_FIELD_* from minicc.task_contract:\n"
        + "\n".join(offenders)
    )
