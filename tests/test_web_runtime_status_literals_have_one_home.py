"""M8-T646 — web runtime_status task-state literals use protocol homes.

`runtime_status` derived from task execution outcome in `minicc.web` is the
same task-status fact as `TASK_STATUS_*`. Verification/graph/LLM status domains
are different facts.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCOPED = {REPO / "minicc" / "web.py"}


def test_no_bare_runtime_status_task_literals() -> None:
    src = (REPO / "minicc" / "web.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    offenders = []
    lines = src.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "runtime_status":
                    # check string constants in the value
                    for n in ast.walk(node.value):
                        if isinstance(n, ast.Constant) and n.value in {"cancelled", "failed", "completed"}:
                            offenders.append(f"minicc/web.py:{n.lineno}: {lines[n.lineno-1].strip()[:160]}")
    offenders = sorted(set(offenders))
    assert offenders == [], (
        "bare task-status literal in runtime_status - use TASK_STATUS_* from minicc.agent.protocol:\n"
        + "\n".join(offenders)
    )
