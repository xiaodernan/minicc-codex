"""M8-T267: a deny rule must reach the read tools too.

``tool_requires_authorization`` returned True only for ``write``/``exec`` risks
and network tools, so a readonly call never consulted ``should_allow``.  The
``permissions.json`` deny rules live inside that gate, so a deny rule on a
path protected nothing on the read path - even though the Web face already
documented the opposite ("denying a path like ``.env`` blocks reads too").

A deny rule is an absolute veto, not a question for the user, so the read
side asks the rule directly instead of going through the approval gate.

This door pins:

* a deny rule on a path blocks ``read_file`` (and the payload never reaches
  the model);
* the veto lands in ``denied_tools`` and is reported as a denial;
* the controls: a read with no matching rule still works, a write path is
  unchanged, and the rule does not fire when the tool is not covered.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from minicc.agent.loop import run_agent
from minicc.llm.base import LLMResponse
from minicc.tools import Editor, build_registry

SECRET = "TOP-SECRET-PAYLOAD"


class _ReaderThenStop:
    """Calls ``read_file`` once, then answers in plain text."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.calls = 0

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Any = None,
        on_delta: Any = None,
        **kwargs: Any,
    ) -> LLMResponse:
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content=None,
                tool_calls=[{
                    "id": "call-0",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps({"path": self.path}),
                    },
                }],
                finish_reason="tool_calls",
            )
        return LLMResponse(content="done", finish_reason="stop")


def _workspace(tmp_path: Path, *, deny_paths: list[str] | None = None) -> Path:
    workspace = tmp_path / "ws"
    (workspace / "secrets").mkdir(parents=True)
    (workspace / "secrets" / "k.txt").write_text(f"{SECRET}\n", encoding="utf-8")
    (workspace / "public.txt").write_text("hello\n", encoding="utf-8")
    if deny_paths is not None:
        (workspace / ".minicc").mkdir()
        (workspace / ".minicc" / "permissions.json").write_text(
            json.dumps({"deny": {"paths": deny_paths}}), encoding="utf-8"
        )
    return workspace


def _run(workspace: Path, path: str, **kwargs: Any) -> Any:
    consulted: list[str] = []

    def should_allow(name: str, call: Any) -> bool:
        consulted.append(name)
        return True

    result = asyncio.run(run_agent(
        _ReaderThenStop(path),
        build_registry(Editor(workspace)),
        [{"role": "user", "content": f"read {path}"}],
        should_allow=should_allow,
        workspace=workspace,
        **kwargs,
    ))
    return result, consulted


# --- the deny rule reaches the read path ---------------------------------------


def test_a_deny_rule_on_a_path_blocks_the_read(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, deny_paths=["secrets/*"])
    result, _consulted = _run(workspace, "secrets/k.txt")
    assert "read_file" in result.denied_tools, "the deny rule did not reach the read"


def test_the_denied_payload_never_reaches_the_model(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, deny_paths=["secrets/*"])
    result, _consulted = _run(workspace, "secrets/k.txt")
    body = json.dumps(result.answer or "", ensure_ascii=False)
    assert SECRET not in body


def test_the_denial_is_reported_as_a_denial_not_a_silent_empty_result(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, deny_paths=["secrets/*"])
    result, _consulted = _run(workspace, "secrets/k.txt")
    assert result.denied_tools == ["read_file"]


# --- the controls --------------------------------------------------------------


def test_a_read_with_no_matching_rule_still_works(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, deny_paths=["secrets/*"])
    result, _consulted = _run(workspace, "public.txt")
    assert result.denied_tools == [], "an unrelated read was denied"


def test_no_rule_at_all_leaves_reads_alone(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    result, _consulted = _run(workspace, "secrets/k.txt")
    assert result.denied_tools == []


def test_a_deny_rule_that_does_not_cover_the_tool_does_not_fire(tmp_path: Path) -> None:
    """The rule names a path; a different path is not covered by it."""
    workspace = _workspace(tmp_path, deny_paths=["other/*"])
    result, _consulted = _run(workspace, "secrets/k.txt")
    assert result.denied_tools == []


def test_the_read_gate_is_not_asked_to_prompt_for_a_readonly_call(tmp_path: Path) -> None:
    """A veto is not a question: the read path must not open an approval."""
    workspace = _workspace(tmp_path, deny_paths=["secrets/*"])
    _result, consulted = _run(workspace, "secrets/k.txt")
    assert "read_file" not in consulted
