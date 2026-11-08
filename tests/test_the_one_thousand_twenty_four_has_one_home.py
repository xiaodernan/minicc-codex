"""M8-T599 — the 1024 trace-event retention cap has one home.

"1024" is the trace-events retention width, and it was spelled in four
places: ``state.py``'s ``MAX_TRACE_EVENTS`` (the AgentState trim),
``loop.py``'s ``MAX_RESULT_TRACE_EVENTS`` (the TurnResult trim, identical
value), ``protocol.py``'s ``EventLog.__init__`` default, and
``task_manager.py``'s merge helper's slice.  A width change meant editing
all four by hand.

``state.py`` is the home (``MAX_TRACE_EVENTS``); everything asks it.  The
64-width per-binding entry caps belong to the loop module's own two named
constants (``MAX_RESULT_USAGE_ENTRIES`` / ``MAX_RESULT_COMPACTION_ENTRIES``),
pinned by their own Python↔JS gate.  The tool-denial ring (``denied_tools``)
is deliberately a *different fact* and keeps its own narrow width; the MB
units in the attachment caps are a different fact and live where they always
did.

This gate pins:

* the home defines exactly that value;
* no int 1024 survives in ``loop.py`` or ``protocol.py`` (the trace cap is
  their ask, not their spelling);
* ``task_manager.py``'s merge trims slice by ``MAX_TRACE_EVENTS``, never by
  a literal 1024.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "agent" / "state.py"
LOOP = PACKAGE / "agent" / "loop.py"
PROTOCOL = PACKAGE / "agent" / "protocol.py"
TASK_MANAGER = PACKAGE / "task_manager.py"


def test_the_home_defines_max_trace_events() -> None:
    tree = ast.parse(HOME.read_text(encoding="utf-8"), filename=str(HOME))
    found = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "MAX_TRACE_EVENTS" for t in node.targets
        ):
            assert isinstance(node.value, ast.Constant)
            found = node.value.value  # type: ignore[assignment]
    assert found == 1024


def _bare_ints(tree: ast.Module, wanted: int):
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value == wanted:
            yield node.lineno


def test_no_bare_1024_in_loop_and_protocol() -> None:
    offenders: list[str] = []
    for path in (LOOP, PROTOCOL):
        relative = path.relative_to(REPO).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for lineno in _bare_ints(tree, 1024):
            offenders.append(f"{relative}:{lineno}")
    assert offenders == [], (
        "these int 1024 constants are the trace-events retention - ask "
        f"MAX_TRACE_EVENTS from minicc/agent/state.py: {offenders}"
    )


def test_task_manager_trims_by_the_home_not_a_literal() -> None:
    source = TASK_MANAGER.read_text(encoding="utf-8")
    assert "[-MAX_TRACE_EVENTS:]" in source, "the merge helper must trim by the home"
    assert "[-1024:]" not in source, "the merge helper spells the trace cap as a literal"
