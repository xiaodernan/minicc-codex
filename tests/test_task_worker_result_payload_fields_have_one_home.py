"""M8-T649 — task_worker reads task-result payload fields via contract homes.

Only `result.get(...)`/`result[...]` reads of the task result payload are in
scope (state-file keys and response shapes are different facts).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCOPED = {REPO / "minicc" / "task_worker.py"}
FIELDS = {
    "answer": "RESULT_FIELD_ANSWER",
    "error": "RESULT_FIELD_ERROR",
    "tokens_used": "RESULT_FIELD_TOKENS_USED",
}


def test_no_bare_result_payload_field_literals_in_task_worker_reads() -> None:
    src = (REPO / "minicc" / "task_worker.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    lines = src.splitlines()
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or node.value not in FIELDS:
            continue
        parent = parents.get(id(node))
        # result.get("field") or result["field"]
        is_result_read = False
        if isinstance(parent, ast.Call):
            f = parent.func
            if isinstance(f, ast.Attribute) and f.attr == "get":
                if isinstance(f.value, ast.Name) and f.value.id == "result":
                    is_result_read = True
        elif isinstance(parent, ast.Subscript):
            if isinstance(parent.value, ast.Name) and parent.value.id == "result":
                is_result_read = True
        if not is_result_read:
            continue
        offenders.append(f"minicc/task_worker.py:{node.lineno}: {lines[node.lineno-1].strip()[:160]}")
    offenders = sorted(set(offenders))
    assert offenders == [], (
        "bare task-result payload field literal in worker result read - use RESULT_FIELD_* from minicc.task_contract:\n"
        + "\n".join(offenders)
    )
