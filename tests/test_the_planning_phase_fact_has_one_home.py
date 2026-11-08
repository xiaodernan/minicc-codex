"""M8-T636 — runtime phase `planning` (and scoped phase literals) have one home.

Bare `"planning"`/`"merging"` literals used as runtime phase values in
`minicc.agent.loop` and `minicc.task_manager` duplicate the phase fact owned by
`minicc.agent.protocol` (`PHASE_PLANNING`/`PHASE_MERGING`). Budget/routing
*stage* labels in `minicc.web` are a different fact and are out of scope.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
SCOPED = {PACKAGE / "agent" / "loop.py", PACKAGE / "task_manager.py"}
PHASE_LITERALS = {"planning", "merging"}


def test_no_bare_phase_literals_in_scoped_modules() -> None:
    offenders: list[str] = []
    for path in sorted(SCOPED):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value in PHASE_LITERALS:
                offenders.append(
                    f"{rel}:{node.lineno}: {src.splitlines()[node.lineno-1].strip()[:160]}"
                )
    offenders = sorted(set(offenders))
    assert offenders == [], (
        "bare runtime phase literal - use PHASE_* from minicc.agent.protocol "
        "(budget/routing stage labels are a different fact):\n" + "\n".join(offenders)
    )
