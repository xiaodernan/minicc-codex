"""M8-T642 / M8-T666 — task result `cancelled` payload field name has one home.

The result-contract field name `"cancelled"` is shared by `minicc.task_contract`,
`minicc.task_execution` and `minicc.task_manager`. Home is
`minicc.task_contract.RESULT_FIELD_CANCELLED`. Distinct from
`TASK_STATUS_CANCELLED` (status value fact).

`minicc.task_manager` also carries the cross-process **cancel-flag IPC**
literal — the bytes the host writes to `.minicc/cancel/<id>.flag` for the
worker to poll. That is an on-disk protocol between two processes, not a
task-result payload field, and it intentionally keeps the bare spelling.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCOPED = {
    REPO / "minicc" / "task_contract.py",
    REPO / "minicc" / "task_execution.py",
    REPO / "minicc" / "task_manager.py",
    REPO / "minicc" / "task_worker.py",
}
HOME = REPO / "minicc" / "task_contract.py"
VAL = "cancelled"
DEF_NAME = "RESULT_FIELD_CANCELLED"


def _is_cancel_flag_ipc(parent: ast.AST | None) -> bool:
    """True for the `.minicc/cancel/<id>.flag` write sites.

    Both call sites spell it as a bare literal inside
    ``cancel_file.write_text("cancelled", encoding="utf-8")`` — a file the
    worker polls, so the two processes need the exact bytes.
    """
    if not isinstance(parent, ast.Call):
        return False
    func = parent.func
    return isinstance(func, ast.Attribute) and func.attr == "write_text"


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
            if path == REPO / "minicc" / "task_manager.py" and _is_cancel_flag_ipc(parent):
                # The host writes the bare word into `.minicc/cancel/<id>.flag`
                # for the worker process to read.  That is an on-disk protocol,
                # not a result-contract field — keep the spelling, keep it bare.
                continue
            offenders.append(f"{rel}:{node.lineno}: {src.splitlines()[node.lineno-1].strip()[:160]}")
    offenders = sorted(set(offenders))
    assert offenders == [], (
        "bare task-result cancelled field literal - use RESULT_FIELD_CANCELLED "
        "from minicc.task_contract (distinct from TASK_STATUS_CANCELLED):\n"
        + "\n".join(offenders)
    )
