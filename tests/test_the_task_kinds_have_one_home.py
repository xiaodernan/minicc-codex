"""M8-T621 — task kind vocabulary has one home.

Task kinds (task, batch, subtask) are compared and assigned across
`minicc.task_manager` and `minicc.web`. Bare string literals duplicate the
same lifecycle/routing fact. The one home is `minicc.agent.protocol`.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "agent" / "protocol.py"
SCOPED = {PACKAGE / "task_manager.py", PACKAGE / "web.py"}

KINDS = {"task", "batch", "subtask"}
HOME_CONST_NAMES = {"TASK_KIND_TASK", "TASK_KIND_BATCH", "TASK_KIND_SUBTASK"}


def test_the_home_defines_task_kind_constants() -> None:
    import minicc.agent.protocol as p

    assert p.TASK_KIND_TASK == "task"
    assert p.TASK_KIND_BATCH == "batch"
    assert p.TASK_KIND_SUBTASK == "subtask"
    assert p.TASK_KINDS == {
        p.TASK_KIND_TASK,
        p.TASK_KIND_BATCH,
        p.TASK_KIND_SUBTASK,
    }


def test_no_bare_task_kind_literals_in_scoped_modules() -> None:
    offenders: list[str] = []
    for path in sorted(SCOPED):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
        lines = src.splitlines()
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or node.value not in KINDS:
                continue
            line = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
            if "task_kind" not in line and "_task_kind" not in line:
                continue
            offenders.append(f"{rel}:{node.lineno} bare task kind {node.value!r}: {line.strip()[:120]}")
    offenders = sorted(set(offenders))
    assert offenders == [], (
        "bare task kind literals in scoped modules - ask "
        "TASK_KIND_* from minicc.agent.protocol:\n" + "\n".join(offenders)
    )
