"""M8-T388 — 写后检视工具 {read_file, git_diff}：loop.py 记录它，completion.py 问它，各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/agent/loop.py"

INSPECTION_TOOL_NAMES = frozenset({"read_file", "git_diff"})


def test_the_home_exists_in_loop() -> None:
    """loop.py owns the inspection tool names with both members."""
    from minicc.agent.loop import INSPECTION_TOOL_NAMES as Home

    assert Home == INSPECTION_TOOL_NAMES


def test_completion_asks_the_home() -> None:
    """completion.py uses the same object, not its own spelling."""
    import minicc.agent.completion as completion
    import minicc.agent.loop as loop

    assert completion.INSPECTION_TOOL_NAMES is loop.INSPECTION_TOOL_NAMES


def test_no_module_inlines_the_inspection_tools() -> None:
    """No module spells the pair as a literal outside the one declaration."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Set | ast.Tuple | ast.List):
                continue
            elements = frozenset(
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
            if len(node.elts) >= 2 and elements == INSPECTION_TOOL_NAMES:
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the inspection tools are spelled inline outside the one declaration: "
        + ", ".join(offenders)
    )


def test_the_gate_still_accepts_an_inspected_write() -> None:
    """The completion gate still counts a post-write inspection from the home."""
    from minicc.agent.completion import CompletionDecision, _enforce_completion_evidence

    # A documentation write is the shape where post-write inspection is the
    # available evidence class (no checker can say anything about prose).
    events = [
        {"kind": "tool", "name": "write_file", "status": "ok", "write": True, "path": "README.md"},
        {"kind": "tool", "name": "read_file", "status": "ok", "path": "README.md"},
    ]
    decision = _enforce_completion_evidence(
        CompletionDecision(status="complete", evidence=["event-1"]),
        events,
        [],
        allow_changes=True,
    )
    assert decision.status == "complete"

    uninspected = _enforce_completion_evidence(
        CompletionDecision(status="complete", evidence=["event-1"]),
        [{"kind": "tool", "name": "write_file", "status": "ok", "write": True, "path": "README.md"}],
        [],
        allow_changes=True,
    )
    assert uninspected.status == "continue"
    assert uninspected.missing
