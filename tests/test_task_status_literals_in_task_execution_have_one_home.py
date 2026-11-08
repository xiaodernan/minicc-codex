"""M8-T637 — task snapshot status literals in task_execution use protocol homes.

`minicc.task_execution` reads task snapshot statuses (`cancelled`, `interrupted`)
that are the same fact as `minicc.agent.protocol.TASK_STATUS_*`. Bare literals
duplicate that fact. Verifier/graph/LLM/benchmark status domains are different
facts and out of scope.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCOPED = {REPO / "minicc" / "task_execution.py"}
STATUS_VALUES = {
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    "interrupted",
    "pending",
}


def test_no_bare_task_status_literals_in_scoped_modules() -> None:
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
            if not isinstance(node, ast.Constant) or node.value not in STATUS_VALUES:
                continue
            parent = parents.get(id(node))
            # Dict key names (payload schema fields) are a different fact from
            # task status code values.
            if isinstance(parent, ast.Dict) and node in parent.keys:
                continue
            offenders.append(
                f"{rel}:{node.lineno}: {src.splitlines()[node.lineno-1].strip()[:160]}"
            )
    offenders = sorted(set(offenders))
    assert offenders == [], (
        "bare task status literal - use TASK_STATUS_* from minicc.agent.protocol:\n"
        + "\n".join(offenders)
    )
