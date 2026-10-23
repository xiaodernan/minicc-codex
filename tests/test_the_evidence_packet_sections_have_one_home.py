"""M8-T393 — 证据包三格：packet_ids 与 citable_ids 两个推导式各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/agent/completion.py"

SECTIONS = frozenset({"events", "verification_results", "conversation"})


def test_the_home_exists_in_completion() -> None:
    """completion.py owns the three packet sections."""
    from minicc.agent.completion import EVIDENCE_PACKET_SECTIONS

    assert EVIDENCE_PACKET_SECTIONS == ("events", "verification_results", "conversation")


def test_no_module_inlines_the_sections() -> None:
    """No module spells the three sections as a literal outside the one declaration."""
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
            if len(node.elts) >= 2 and elements == SECTIONS:
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the evidence packet sections are spelled inline outside the one declaration: "
        + ", ".join(offenders)
    )


def test_both_id_sets_still_cover_every_section() -> None:
    """A conversation transcript entry is addressable and citable, like an event."""
    from minicc.agent.completion import (
        CompletionDecision,
        _enforce_completion_evidence,
        _evidence_packet,
    )

    events = [
        {"kind": "tool", "name": "write_file", "status": "ok", "write": True, "path": "README.md"},
        {"kind": "tool", "name": "read_file", "status": "ok", "path": "README.md"},
    ]
    messages = [{"role": "user", "content": "please update the readme"}]
    packet = _evidence_packet(events, [], messages)
    assert '"conversation"' in packet
    decision = _enforce_completion_evidence(
        CompletionDecision(status="complete", evidence=["event-1"]),
        events,
        [],
        messages,
        allow_changes=True,
    )
    assert decision.status == "complete"
