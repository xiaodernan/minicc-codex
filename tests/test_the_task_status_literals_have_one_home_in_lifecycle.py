"""M8-T616 — task lifecycle status comparisons ask the protocol home.

Task lifecycle modules (task_manager, task_worker) compared statuses to bare
string literals like ``== "cancelled"`` / ``!= "interrupted"`` even though the
vocabulary is homed in ``minicc.agent.protocol`` (``TASK_STATUSES``,
``TASK_STATUS_*``).  This is scoped narrowly to lifecycle modules to avoid
conflating lookalike status vocabularies in other domains (tool results,
verification results, DAG node results).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "agent" / "protocol.py"
SCOPED = {PACKAGE / "task_manager.py", PACKAGE / "task_worker.py"}

STATUSES = {"queued", "running", "completed", "failed", "cancelled", "interrupted"}


def test_the_home_defines_individual_status_constants() -> None:
    import minicc.agent.protocol as p

    assert p.TASK_STATUS_QUEUED == "queued"
    assert p.TASK_STATUS_RUNNING == "running"
    assert p.TASK_STATUS_COMPLETED == "completed"
    assert p.TASK_STATUS_FAILED == "failed"
    assert p.TASK_STATUS_CANCELLED == "cancelled"
    assert p.TASK_STATUS_INTERRUPTED == "interrupted"
    assert p.TASK_STATUSES == {
        p.TASK_STATUS_QUEUED, p.TASK_STATUS_RUNNING, p.TASK_STATUS_COMPLETED,
        p.TASK_STATUS_FAILED, p.TASK_STATUS_CANCELLED, p.TASK_STATUS_INTERRUPTED,
    }
    assert p.TERMINAL_TASK_STATUSES == {
        p.TASK_STATUS_COMPLETED, p.TASK_STATUS_FAILED, p.TASK_STATUS_CANCELLED, p.TASK_STATUS_INTERRUPTED,
    }
    assert p.TASK_UNSUCCESSFUL_STATUSES == {p.TASK_STATUS_FAILED, p.TASK_STATUS_INTERRUPTED}


def test_no_bare_task_status_comparisons_in_lifecycle_modules() -> None:
    offenders: list[str] = []
    for path in sorted(SCOPED):
        try:
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src, filename=str(path))
        except Exception:
            continue
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                for op, comp in zip(node.ops, node.comparators):
                    if isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(comp, ast.Constant) and comp.value in STATUSES:
                        offenders.append(f"{rel}:{comp.lineno} compares to {comp.value!r}")
                if isinstance(node.left, ast.Constant) and node.left.value in STATUSES:
                    for op in node.ops:
                        if isinstance(op, (ast.Eq, ast.NotEq)):
                            offenders.append(f"{rel}:{node.left.lineno} compares {node.left.value!r}")
                            break
    assert offenders == [], (
        "bare task status comparisons in lifecycle modules - ask TASK_STATUS_* "
        "from minicc.agent.protocol:\n" + "\n".join(offenders)
    )


def test_no_bare_task_status_dict_literals_in_lifecycle_modules() -> None:
    offenders: list[str] = []
    for path in sorted(SCOPED):
        try:
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src, filename=str(path))
        except Exception:
            continue
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values):
                    if (
                        isinstance(k, ast.Constant)
                        and k.value == "status"
                        and isinstance(v, ast.Constant)
                        and v.value in STATUSES
                    ):
                        offenders.append(f"{rel}:{v.lineno} dict status {v.value!r}")
    assert offenders == [], (
        "bare task status dict literals in lifecycle modules - ask TASK_STATUS_* "
        "from minicc.agent.protocol:\n" + "\n".join(offenders)
    )
