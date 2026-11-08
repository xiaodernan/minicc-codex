"""M8-T639 — `budget_exceeded_event` subagent stage label has one home.

The `"subagent"` stage/name passed to `budget_exceeded_event` in `minicc.main`
and `minicc.web` is the same cross-module budget-stage fact. Home is
`minicc.agent.protocol.BUDGET_STAGE_SUBAGENT`. Other stage labels that appear
in only one module are out of scope until they duplicate.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOME = REPO / "minicc" / "agent" / "protocol.py"
SCOPED = {REPO / "minicc" / "main.py", REPO / "minicc" / "web.py"}


def test_the_home_defines_budget_stage_subagent() -> None:
    from minicc.agent.protocol import BUDGET_STAGE_SUBAGENT

    assert BUDGET_STAGE_SUBAGENT == "subagent"


def _is_budget_exceeded_call(node: ast.Call) -> bool:
    f = node.func
    return (isinstance(f, ast.Name) and f.id == "budget_exceeded_event") or (
        isinstance(f, ast.Attribute) and f.attr == "budget_exceeded_event"
    )


def test_no_bare_subagent_budget_stage_in_scoped_call_sites() -> None:
    offenders: list[str] = []
    for path in sorted(SCOPED):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_budget_exceeded_call(node):
                continue
            values = [a for a in node.args if isinstance(a, ast.Constant)]
            values += [k.value for k in node.keywords if isinstance(k.value, ast.Constant)]
            for v in values:
                if v.value == "subagent":
                    offenders.append(
                        f"{rel}:{v.lineno}: {src.splitlines()[v.lineno-1].strip()[:160]}"
                    )
    offenders = sorted(set(offenders))
    assert offenders == [], (
        "bare subagent budget stage/name literal - use BUDGET_STAGE_SUBAGENT "
        "from minicc.agent.protocol:\n" + "\n".join(offenders)
    )
