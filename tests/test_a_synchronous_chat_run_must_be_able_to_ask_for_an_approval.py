"""M8-T289: a synchronous chat run must be able to ask for an approval.

``/api/chat`` has no event stream: the run's events come back in the
response body.  The approval frame is the one event the client cannot do
without - it carries the ``request_id`` that ``POST /api/approval`` needs
in order to answer.

The fallback sink for a run without a stream only *logged* its events, so
the approval frame went nowhere the caller could see.  The run blocked for
the full approval timeout, denied itself, and the client could not have
answered even if it had wanted to.

This door pins:

* the approval frame reaches the caller;
* the run's own events are not duplicated by the fallback sink.
"""

from __future__ import annotations

import json
import threading
import time
import types
from pathlib import Path
from typing import Any

import pytest

from minicc.web import AgentService


def _config() -> types.SimpleNamespace:
    return types.SimpleNamespace(
        yolo=False,
        max_concurrent_tasks=2,
        sandbox_mode="host",
        sandbox_image="python:3.11-slim",
        base_url="https://example.test/v1",
        api_key="test-key",
        model="test-model",
        timeout=10,
        tool_mode="auto",
        reasoning_effort="high",
        max_turns=4,
        compact_threshold=300_000,
        context_window_tokens=300_000,
    )


class _WritesFileProvider:
    """Asks for a write, which needs the task-level grant."""

    def __init__(self, **_kwargs: Any) -> None:
        self.calls = 0

    async def chat(self, messages, tools=None, on_delta=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return _tool_result("write_file", {"path": "b.txt", "content": "x\n"})
        return _plain("done")

    async def close(self) -> None:
        return None


def _tool_result(name: str, arguments: dict[str, Any]) -> Any:
    from minicc.llm.base import LLMResponse

    return LLMResponse(
        content=None,
        tool_calls=[{
            "id": "call-0",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)},
        }],
        finish_reason="tool_calls",
    )


def _plain(text: str) -> Any:
    from minicc.llm.base import LLMResponse

    return LLMResponse(content=text, finish_reason="stop")


def test_the_approval_frame_reaches_the_caller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The frame with the request_id must be in the returned events."""
    monkeypatch.setattr("minicc.web.OpenAICompatibleProvider", _WritesFileProvider)
    monkeypatch.setattr("minicc.web.APPROVAL_TIMEOUT_SECONDS", 2.0)
    service = AgentService(tmp_path, _config())
    try:
        result = service._chat_locked(
            {
                "message": "在 b.txt 里写一行",
                "session_id": "approval-frame",
                "allow_changes": False,
                "workspace_path": str(tmp_path),
            },
            workspace=tmp_path,
        )
    finally:
        service.shutdown()

    events = result.get("events") or []
    approvals = [
        event for event in events
        if isinstance(event, dict) and event.get("kind") == "approval_request"
    ]
    assert approvals, (
        "the approval frame never reached the caller; the client cannot answer "
        f"without it (events: {len(events)})"
    )
    assert approvals[0].get("request_id"), "the approval frame carries no request id"


def test_the_fallback_sink_does_not_duplicate_the_runs_own_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: the run's events are not counted twice.

    The run's own events reach the sink through the ``on_event(events[-1])``
    pattern, so a sink that collected *everything* would double every
    entry - and the completion layer counts tool events to decide whether
    the run has produced anything new.
    """
    monkeypatch.setattr("minicc.web.OpenAICompatibleProvider", _WritesFileProvider)
    monkeypatch.setattr("minicc.web.APPROVAL_TIMEOUT_SECONDS", 2.0)
    service = AgentService(tmp_path, _config())
    try:
        result = service._chat_locked(
            {
                "message": "在 b.txt 里写一行",
                "session_id": "no-duplicates",
                "allow_changes": False,
                "workspace_path": str(tmp_path),
            },
            workspace=tmp_path,
        )
    finally:
        service.shutdown()

    events = [event for event in (result.get("events") or []) if isinstance(event, dict)]
    # Identity, not content: several events legitimately share a code
    # (``model_decision`` once per turn).
    identities = [id(event) for event in events]
    assert len(identities) == len(set(identities)), (
        "the fallback sink duplicated the run's events"
    )
