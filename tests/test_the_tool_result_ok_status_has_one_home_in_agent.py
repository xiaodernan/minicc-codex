"""M8-T622 — tool result "ok" status comparisons in agent modules use one home.

Tool result status is owned by `minicc.tools.schemas` (`TOOL_STATUS_OK`,
M8-T618). Agent modules that compare tool/search result `.status` to the bare
literal `"ok"` duplicate that fact. Scoped to `ast.Compare` comparators in the
agent modules that gate on tool outcomes, to avoid conflating verification/event
status vocabularies that also use the string "ok" as a different fact.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
SCOPED = {
    PACKAGE / "agent" / "loop.py",
    PACKAGE / "agent" / "tool_policy.py",
    PACKAGE / "agent" / "verifier.py",
}


def test_no_bare_ok_tool_result_comparisons_in_scoped_agent_modules() -> None:
    offenders: list[str] = []
    for path in sorted(SCOPED):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            for comp in node.comparators:
                if isinstance(comp, ast.Constant) and comp.value == "ok":
                    offenders.append(f"{rel}:{comp.lineno}: {src.splitlines()[comp.lineno-1].strip()[:140]}")
    offenders = sorted(set(offenders))
    assert offenders == [], (
        'bare tool-result "ok" comparison - ask TOOL_STATUS_OK from minicc.tools.schemas:\n'
        + "\n".join(offenders)
    )
