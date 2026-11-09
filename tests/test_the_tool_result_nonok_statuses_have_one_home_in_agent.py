"""M8-T623 — tool result non-ok status comparisons in agent modules use one home.

Tool result statuses are owned by `minicc.tools.schemas` (M8-T618). Agent code
that compares a tool/search *result object*'s `.status` to bare literals like
`"error"`, `"denied"`, `"cancelled"`, `"timed_out"` duplicates that fact.

Scoped tightly to `ast.Compare` where the compared value is `<*_result>.status`
(a `ToolResult`/search result object), to avoid conflating verification statuses,
task statuses, or event-status fields that share string values.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
SCOPED = {
    PACKAGE / "agent" / "loop.py",
    PACKAGE / "agent" / "verifier.py",
}
TOOL_STATS = {"error", "denied", "cancelled", "timed_out"}


def _is_result_status_attr(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "status"
        and isinstance(node.value, ast.Name)
        and "result" in node.value.id
    )


def test_no_bare_tool_result_status_literals_on_result_objects_in_scoped_modules() -> None:
    offenders: list[str] = []
    for path in sorted(SCOPED):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            sides = [node.left] + list(node.comparators)
            if not any(_is_result_status_attr(s) for s in sides):
                continue
            for comp in node.comparators:
                if isinstance(comp, ast.Constant) and comp.value in TOOL_STATS:
                    offenders.append(
                        f"{rel}:{comp.lineno}: {src.splitlines()[comp.lineno-1].strip()[:150]}"
                    )
    offenders = sorted(set(offenders))
    assert offenders == [], (
        "bare tool-result status literal on a result object - ask TOOL_STATUS_* "
        "from minicc.tools.schemas:\n" + "\n".join(offenders)
    )


def test_no_bare_tool_result_status_literals_on_tool_result_calls_in_core_agent_modules() -> None:
    """Construction sites are the other half of the fact.

    ``ToolResult(status="cancelled")`` in core agent modules is the exact same
    spelling the schema home already owns.  This leg covers calls named
    ``ToolResult`` with a bare literal ``status=`` keyword — comparisons alone
    left construction sites invisible to the census (M8-T679).
    """
    offenders: list[str] = []
    scoped = sorted(PACKAGE.rglob("*.py"))
    for path in scoped:
        rel = path.relative_to(REPO).as_posix()
        if not (rel.startswith("agent/") or rel.startswith("tools/")):
            continue
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not (isinstance(node.func, ast.Name) and node.func.id == "ToolResult"):
                continue
            for keyword in node.keywords:
                if keyword.arg != "status":
                    continue
                value = keyword.value
                if isinstance(value, ast.Constant) and value.value in TOOL_STATS:
                    offenders.append(
                        f"{rel}:{value.lineno}: {src.splitlines()[value.lineno-1].strip()[:150]}"
                    )
    offenders = sorted(set(offenders))
    assert offenders == [], (
        "bare tool-result status literal on a ToolResult call - use TOOL_STATUS_* "
        "from minicc.tools.schemas:\n" + "\n".join(offenders)
    )
