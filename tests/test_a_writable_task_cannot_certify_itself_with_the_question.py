"""M8-T283: a task that was allowed to change the workspace cannot certify
itself with the user's own question.

The conversation bucket was unconditionally citable, so a review could point
at ``message-1`` - the user's own request - and a task that was *allowed* to
change the workspace and changed **nothing** came back as complete.  The
same exemption made the "nothing happened at all" fallback unreachable, so
the one guard that should have caught this never ran.

The conversation is legitimate evidence when the task was about the
conversation (recall, summary) and when the run already produced real work.
It is not a substitute for the work a writable task was supposed to do.

This door pins:

* a writable task with no work at all is sent back, not certified;
* the control: a read-only task with no work may still be complete (a recall
  or summary request is a legitimate no-tool task);
* a writable task that did produce work may cite the conversation.
"""

from __future__ import annotations

from typing import Any

from minicc.agent.completion import CompletionDecision, _enforce_completion_evidence

MESSAGES: list[dict[str, Any]] = [
    {"role": "system", "content": "sys"},
    {"role": "user", "content": "请修复 app.py 里的 bug"},
    {"role": "assistant", "content": "好的，我来修。"},
]


def _decision() -> CompletionDecision:
    return CompletionDecision(
        status="complete",
        confidence=0.9,
        rationale="done",
        missing=[],
        next_action="",
        evidence=["message-1"],
    )


def test_a_writable_task_with_no_work_is_sent_back() -> None:
    """The hole: nothing was done, and the user's question was cited."""
    decision = _enforce_completion_evidence(
        _decision(), [], [], MESSAGES, allow_changes=True
    )
    assert decision.status == "continue", (
        "a task that changed nothing certified itself with the user's question"
    )
    assert decision.missing, "the gap was not named"


def test_a_read_only_task_with_no_work_may_still_be_complete() -> None:
    """The control: a recall or summary request is a legitimate no-tool task."""
    decision = _enforce_completion_evidence(
        _decision(), [], [], MESSAGES, allow_changes=False
    )
    assert decision.status == "complete"


def test_a_writable_task_that_produced_work_may_cite_the_conversation() -> None:
    """A real write *and* a real check after it are the evidence."""
    events = [
        {
            "kind": "tool",
            "name": "write_file",
            "write": True,
            "status": "ok",
            "path": "app.py",
        },
        {
            "kind": "tool",
            "name": "bash",
            "status": "ok",
            "command": "python -m pytest -q",
        },
    ]
    decision = _enforce_completion_evidence(
        _decision(), events, [], MESSAGES, allow_changes=True
    )
    assert decision.status == "complete"


def test_a_writable_task_with_a_failing_verification_is_sent_back() -> None:
    """The control that must keep working: a failed check wins."""
    decision = _enforce_completion_evidence(
        _decision(),
        [],
        [{"command": "python -m pytest", "status": "failed"}],
        MESSAGES,
        allow_changes=False,
    )
    assert decision.status == "continue"
