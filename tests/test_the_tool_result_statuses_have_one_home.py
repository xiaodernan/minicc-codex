"""M8-T618 — ToolResult status literals in tool implementations ask the home.

``minicc/tools/schemas.py`` owns the tool result status vocabulary
(`TOOL_RESULT_STATUSES` and individual `TOOL_STATUS_*` constants).  Tool
implementations that construct ``ToolResult(status="...")`` with those values
must use the constants.  Scoped to ``ToolResult(...)`` constructor calls under
``minicc/tools/`` to avoid conflating lookalike status vocabularies in other
domains (verification results, DAG nodes, etc.).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / "minicc" / "tools"
HOME = TOOLS / "schemas.py"

STATUSES = {"ok", "error", "denied", "cancelled", "timed_out"}


def test_the_home_defines_individual_constants() -> None:
    from minicc.tools.schemas import (
        TOOL_STATUS_OK, TOOL_STATUS_ERROR, TOOL_STATUS_DENIED,
        TOOL_STATUS_CANCELLED, TOOL_STATUS_TIMED_OUT, TOOL_RESULT_STATUSES,
        FAILED_TOOL_RESULT_STATUSES, UNSUCCESSFUL_TOOL_RESULT_STATUSES,
    )
    assert TOOL_STATUS_OK == "ok"
    assert TOOL_STATUS_ERROR == "error"
    assert TOOL_STATUS_DENIED == "denied"
    assert TOOL_STATUS_CANCELLED == "cancelled"
    assert TOOL_STATUS_TIMED_OUT == "timed_out"
    assert set(TOOL_RESULT_STATUSES) == STATUSES
    assert FAILED_TOOL_RESULT_STATUSES == {"error", "denied", "timed_out"}
    assert UNSUCCESSFUL_TOOL_RESULT_STATUSES == {"error", "denied", "cancelled", "timed_out"}


def test_no_bare_tool_result_status_literals_in_tools() -> None:
    offenders: list[str] = []
    for path in sorted(TOOLS.rglob("*.py")):
        if path.resolve() == HOME.resolve():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception:
            continue
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else "")
                if name != "ToolResult":
                    continue
                for kw in node.keywords:
                    if kw.arg == "status" and isinstance(kw.value, ast.Constant) and kw.value.value in STATUSES:
                        offenders.append(f"{rel}:{kw.value.lineno} ToolResult(status={kw.value.value!r})")
    assert offenders == [], (
        "bare ToolResult(status=...) literals under minicc/tools/ - ask "
        "TOOL_STATUS_* from minicc.tools.schemas:\n" + "\n".join(offenders)
    )
