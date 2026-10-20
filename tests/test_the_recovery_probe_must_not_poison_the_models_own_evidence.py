"""M8-T282: the recovery probe must not poison the model's own evidence.

When the loop detects stagnation it runs a *recovery probe*: the same
read-only tools the model is then told to use, so the model sees the actual
state instead of an abstract "try harder".  The probe's results were cached.

But the recovery guard asks for evidence that is **not a duplicate** - and
``git_status`` takes no arguments, so the model's own call has exactly the
probe's signature.  The cache therefore turned the model's fresh call into
a ``[DUPLICATE_TOOL_CALL]``, the guard stayed unsatisfied, and the task
could only end by exhausting the stagnation limit.  The probe had locked the
very door it was opened to unlock.

The probe is a diagnostic, not a reusable result.

This door pins:

* after a recovery probe, the model's own identical call is not a duplicate;
* the control: an ordinary repeated call is still a duplicate.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from minicc.agent.loop import run_agent
from minicc.llm.base import LLMResponse
from minicc.tools import build_registry
from minicc.tools.editor import Editor


class _ScriptedProvider:
    """Runs a fixed list of turns, then answers in plain text."""

    def __init__(self, turns: list[dict[str, Any]]) -> None:
        self.turns = list(turns)
        self.calls = 0

    async def chat(self, messages, tools=None, on_delta=None, **kwargs):
        if self.calls >= len(self.turns):
            return LLMResponse(content="done", finish_reason="stop")
        turn = self.turns[self.calls]
        self.calls += 1
        return LLMResponse(
            content=turn.get("content"),
            tool_calls=turn.get("tool_calls") or [],
            finish_reason=turn.get("finish_reason", "tool_calls"),
        )


def _call(name: str, arguments: dict[str, Any], call_id: str) -> dict[str, Any]:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


def _duplicate_flags(results: list[dict[str, Any]]) -> list[bool]:
    """Whether each tool result was served from the cache."""
    flags: list[bool] = []
    for event in results:
        data = event.get("data") if isinstance(event, dict) else None
        if isinstance(data, dict) and data.get("duplicate"):
            flags.append(True)
        else:
            flags.append(False)
    return flags


def _run(workspace: Path, provider: _ScriptedProvider) -> tuple[Any, list[dict[str, Any]]]:
    tool_events: list[dict[str, Any]] = []

    def on_tool(call: Any, result: Any) -> None:
        tool_events.append({
            "tool": call.tool,
            "status": result.status,
            "data": dict(result.data or {}),
            "summary": result.summary,
        })

    result = asyncio.run(run_agent(
        provider,
        build_registry(Editor(workspace)),
        [{"role": "user", "content": "看一下仓库状态"}],
        on_tool=on_tool,
        workspace=workspace,
    ))
    return result, tool_events


def test_the_probes_own_result_does_not_make_the_models_call_a_duplicate(
    tmp_path: Path,
) -> None:
    """The lock the probe used to hold on itself."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "README.md").write_text("# demo\n", encoding="utf-8")

    provider = _ScriptedProvider([
        # The same read three times in a row: the stagnation guard fires (two
        # consecutive identical rounds) and the recovery probe runs
        # ``git_status`` / ``git_diff`` / ``tree``.
        {"tool_calls": [_call("read_file", {"path": "README.md"}, "c1")]},
        {"tool_calls": [_call("read_file", {"path": "README.md"}, "c2")]},
        {"tool_calls": [_call("read_file", {"path": "README.md"}, "c3")]},
        # Now the model answers the recovery request with the same tool the
        # probe used.
        {"tool_calls": [_call("git_status", {}, "c4")]},
    ])
    result, events = _run(workspace, provider)

    git_status_calls = [event for event in events if event["tool"] == "git_status"]
    assert git_status_calls, "the model never called git_status"
    # The first git_status may be the probe's own (which is not a duplicate);
    # the model's follow-up must not be one either.
    assert not any(event["data"].get("duplicate") for event in git_status_calls), (
        "the model's own call was served from the probe's cache entry"
    )


def test_an_ordinary_repeated_call_is_still_a_duplicate(tmp_path: Path) -> None:
    """The control: the reuse guard itself is untouched."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "README.md").write_text("# demo\n", encoding="utf-8")

    provider = _ScriptedProvider([
        {"tool_calls": [_call("read_file", {"path": "README.md"}, "c1")]},
        {"tool_calls": [_call("read_file", {"path": "README.md"}, "c2")]},
    ])
    _result, events = _run(workspace, provider)

    read_calls = [event for event in events if event["tool"] == "read_file"]
    assert len(read_calls) >= 2
    assert any(event["data"].get("duplicate") for event in read_calls), (
        "the ordinary reuse guard stopped working"
    )
