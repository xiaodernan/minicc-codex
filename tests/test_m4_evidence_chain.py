"""M4-T1: evidence-chain regressions.

Four named cases, one per defect the roadmap calls out. Each fails red on the
pre-fix code and green after:

1. a bash command that rewrites the workspace must count as a write
   (``verification_required`` / completion ``write`` flag);
2. editing ``.md`` / extensionless build files must invalidate the verification
   fingerprint instead of reusing a stale pass;
3. a trace event id cannot be cited as completion evidence (a zero-tool
   read-only task cannot self-certify with ``event-1``);
4. the earliest write survives a flood of later events in the evidence packet.
"""

from __future__ import annotations

import json
from pathlib import Path

from minicc.agent.completion import (
    CompletionDecision,
    _enforce_completion_evidence,
    _evidence_packet,
)
from minicc.agent.loop import build_tool_feedback
from minicc.agent.tool_policy import command_may_modify_workspace, is_workspace_write
from minicc.agent.verification_plan import verification_fingerprint
from minicc.tools.schemas import ToolCall, ToolResult


def test_bash_workspace_write_is_flagged_as_write() -> None:
    # The mechanism that trips verification_required and the completion write flag.
    assert command_may_modify_workspace("sed -i 's/a/b/' app.py") is True
    assert command_may_modify_workspace("python patch.py") is True
    assert command_may_modify_workspace("cat app.py") is False
    assert command_may_modify_workspace("pytest tests/") is False

    assert is_workspace_write("bash", {"command": "sed -i x f.py"}, "ok") is True
    assert is_workspace_write("bash", {"command": "cat f.py"}, "ok") is False
    assert is_workspace_write("bash", {"command": "sed -i x f.py"}, "error") is False

    feedback = build_tool_feedback(
        ToolCall(tool="bash", arguments={"command": "sed -i 's/a/b/' app.py"}),
        ToolResult(status="ok", summary="patched"),
    )
    assert feedback["write"] is True


def test_markdown_and_extensionless_edit_invalidates_fingerprint(tmp_path: Path) -> None:
    root = tmp_path
    (root / "notes.md").write_text("# v1\n", encoding="utf-8")
    (root / "Makefile").write_text("all:\n\techo one\n", encoding="utf-8")
    first = verification_fingerprint(root, [], [])
    assert first, "fingerprint must be computable for a small clean tree"

    (root / "notes.md").write_text("# v2 changed\n", encoding="utf-8")
    after_md = verification_fingerprint(root, [], [])
    assert after_md != first, "editing a .md file must change the fingerprint"

    (root / "notes.md").write_text("# v1\n", encoding="utf-8")
    (root / "Makefile").write_text("all:\n\techo two\n", encoding="utf-8")
    # M8-T67: both rewrites above are the same length as what they replace, so this gate used
    # to pass only when the filesystem happened to advance st_mtime_ns - measured at ~32% of
    # rapid writes on this volume, which made it redden in roughly one full run in five for a
    # reason that had nothing to do with the code under test. The timestamps are pushed
    # forward explicitly so the precondition is established rather than gambled on.
    # What this gate therefore does NOT cover: an equal-length edit that lands inside a single
    # timestamp tick. That window is the open M8-T65 / M8-T66 question, and it is stated here
    # rather than papered over by making the edits different lengths.
    import os

    for name in ("notes.md", "Makefile"):
        path = root / name
        stamp = path.stat()
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 2_000_000))
    after_makefile = verification_fingerprint(root, [], [])
    assert after_makefile != first, "editing an extensionless build file must change the fingerprint"


def test_trace_id_cannot_serve_as_completion_evidence() -> None:
    # A zero-tool read-only session: only a narration trace exists.
    events = [
        {
            "kind": "trace",
            "name": "agent",
            "status": "ok",
            "phase": "planning",
            "code": "milestone",
            "summary": "任务已是只读，直接给出结论",
        }
    ]
    decision = CompletionDecision(
        status="complete",
        confidence=0.9,
        rationale="只读任务，无需修改",
        evidence=["event-1"],
    )
    enforced = _enforce_completion_evidence(decision, events, [])
    assert enforced.status == "continue", "a trace id must not certify completion"


def test_earliest_write_survives_event_flood() -> None:
    events: list[dict] = [
        {"kind": "tool", "name": "write_file", "status": "ok", "write": True, "path": "a.py"}
    ]
    # 99 more writes then 5 traces: 105 events, far over the 80-event budget.
    for index in range(99):
        events.append(
            {"kind": "tool", "name": "write_file", "status": "ok", "write": True, "path": f"f{index}.py"}
        )
    for index in range(5):
        events.append({"kind": "trace", "name": "agent", "status": "ok", "summary": f"trace {index}"})

    packet = json.loads(_evidence_packet(events, []))
    ids = {item["id"] for item in packet["events"]}
    assert "event-1" in ids, "the earliest write must remain citable after a flood"
