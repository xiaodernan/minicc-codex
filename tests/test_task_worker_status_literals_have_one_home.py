"""M8-T641 — task_worker task-status literals use protocol homes.

Worker-owned `state["status"]` assignments and `_final_flush` terminal statuses
are task status facts (`TASK_STATUS_*`). `result.get("cancelled")` payload
field access is a different fact and must not be conflated.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCOPED = {REPO / "minicc" / "task_worker.py"}
STATUS_VALUES = {"queued", "running", "completed", "failed", "cancelled", "interrupted"}


def test_no_bare_task_status_literals_in_worker_status_contexts() -> None:
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
            if isinstance(parent, ast.Dict) and node in parent.keys:
                continue
            # allow payload field reads like result.get("cancelled")
            if isinstance(parent, ast.Call):
                func = parent.func
                if isinstance(func, ast.Attribute) and func.attr == "get":
                    continue
            # allow membership/exclusion sets over payload field names
            if isinstance(parent, (ast.Set, ast.List, ast.Tuple)):
                grand = parents.get(id(parent))
                if isinstance(grand, ast.Compare):
                    continue
            offenders.append(
                f"{rel}:{node.lineno}: {src.splitlines()[node.lineno-1].strip()[:160]}"
            )
    offenders = sorted(set(offenders))
    assert offenders == [], (
        "bare task status literal in worker status context - use TASK_STATUS_* "
        "from minicc.agent.protocol (payload field names are a different fact):\n"
        + "\n".join(offenders)
    )
