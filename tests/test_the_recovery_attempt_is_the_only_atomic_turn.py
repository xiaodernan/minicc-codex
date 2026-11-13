"""M8-T879 — the provider-recovery atomic-replay fix scopes to the recovery attempt.

After a transient provider failure, the *recovery* attempt used to run
non-streaming (correct: the interrupted turn may already have delivered deltas
to the UI, and an atomic retry avoids duplicated visible text) — but the latch
never reset, so every later turn of that task ran atomically too, silently
killing incremental output for the rest of the run (the "一直显示非流" the
operator saw).

The fix scopes atomicity to the recovery attempt itself: a completed attempt
is safe ground, so turns after it — a repair round after a failed verification
in particular — stream like any other turn.

This gate drives the real task loop with a fake provider that:

1. writes a file on turn 1 (normal streaming turn, asks for a write tool);
2. raises a transient stream failure on turn 2;
3. on the recreated (recovery) provider, writes the file again and finishes;
4. rides a monkeypatched Verifier that fails the first check and passes the
   second — forcing a repair round after the recovery;
5. records whether ``on_delta`` was non-None for every chat call.

It then asserts: the recovery attempt's calls were atomic, the initial and
the repair round's calls streamed.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from minicc.llm.base import LLMResponse
from minicc.agent.verifier import VerificationResult
from minicc.web import AgentService, OpenAICompatibleProvider  # noqa: F401  (re-export shape pinned elsewhere)


def _write_call(name: str = "write_file") -> list[dict[str, Any]]:
    return [
        {
            "id": "call-write-1",
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(
                    {"path": "recovered.txt", "content": "written by the agent\n"}
                ),
            },
        }
    ]


def _read_call() -> list[dict[str, Any]]:
    return [
        {
            "id": "call-read-1",
            "type": "function",
            "function": {
                "name": "read_file",
                "arguments": json.dumps({"path": "recovered.txt"}),
            },
        }
    ]


def _completion_json(messages: list[dict[str, Any]]) -> str:
    import re as _re

    # The review packet embeds compact JSON whose ids are double-quoted; plain
    # `str(messages)` backslash-escapes them.  A bare token scan is escape-proof.
    evidence = list(dict.fromkeys(_re.findall(r"(?:event|verification)-\d+", str(messages))))[-8:]
    return json.dumps(
        {
            "status": "complete",
            "confidence": 0.99,
            "rationale": "已有充分证据。",
            "missing": [],
            "next_action": "",
            "evidence": evidence,
        }
    )


def test_the_recovery_attempt_is_the_only_atomic_turn(tmp_path, monkeypatch):
    instances: list[object] = []
    chat_streaming: list[tuple[int, bool]] = []  # (provider_index, on_delta_is_not_none)
    stream_deltas: list[str] = []

    state = {"recovery_delivered": False}

    class FakeProvider:
        def __init__(self, **_kwargs) -> None:
            self.index = len(instances)
            self.calls = 0
            instances.append(self)

        async def chat(self, messages, tools, on_delta=None):
            self.calls += 1
            chat_streaming.append((self.index, on_delta is not None))
            if tools is None:  # completion judge rides any provider; tools=None
                return LLMResponse(content=_completion_json(messages))
            if self.index == 0:
                if self.calls == 1:
                    return LLMResponse(tool_calls=_write_call(), finish_reason="tool_calls")
                raise RuntimeError(
                    "stream disconnected before completion: Connection error."
                )
            # Any non-planning provider (recovery/repair round, possibly the
            # same sticky instance): cycle write -> read -> settle so the
            # recovery-inspection guard always gets a real tool round first.
            if self.calls % 3 == 1:
                return LLMResponse(tool_calls=_write_call(), finish_reason="tool_calls")
            if self.calls % 3 == 2:
                return LLMResponse(tool_calls=_read_call(), finish_reason="tool_calls")
            if not state["recovery_delivered"]:
                content = "恢复行内容"
                state["recovery_delivered"] = True
            else:
                content = "修复行内容"
            if on_delta is not None:
                on_delta(content[:2])
                on_delta(content[2:])
            return LLMResponse(content=content)

        def protocol(self) -> str:
            return "chat_completions"

        @staticmethod
        def is_transient_failure(error: str | None) -> bool:
            return OpenAICompatibleProvider.is_transient_failure(error or "")

        def protocol_status(self) -> dict[str, str]:
            return {"active": "chat_completions", "requested": "chat_completions"}

        async def close(self) -> None:
            return None

    monkeypatch.setattr("minicc.web.OpenAICompatibleProvider", FakeProvider)

    verify_calls = {"n": 0}

    class FakeVerifier:
        def run(self, workspace, *, plan=None, allow_project_scripts=True, cancel_event=None):
            verify_calls["n"] += 1
            if verify_calls["n"] == 1:
                return VerificationResult(
                    status="failed",
                    command="pytest -q",
                    output="1 failed",
                    actionable_hint="修复失败后重跑",
                )
            return VerificationResult(status="passed", command="pytest -q", output="passed")

    monkeypatch.setattr("minicc.web.Verifier", lambda: FakeVerifier())
    monkeypatch.setattr("minicc.web.build_verification_plan", lambda *a, **k: SimpleNamespace())

    config = SimpleNamespace(
        yolo=False,
        max_concurrent_tasks=1,
        max_repair_attempts=2,
        task_recovery_retries=1,
        sandbox_mode="host",
        sandbox_image="python:3.11-slim",
        base_url="https://example.test/v1",
        api_key="test-key",
        model="test-model",
        timeout=10,
        tool_mode="auto",
        reasoning_effort="high",
        max_turns=14,
        compact_threshold=300_000,
        context_window_tokens=300_000,
        max_duration_seconds=20,
        max_tool_calls=20,
    )
    service = AgentService(tmp_path, config)
    try:
        result = service._chat_locked(
            {
                "message": "写一个文件并验证",
                "session_id": "recovery-stream-latch",
                "allow_changes": True,
                "workspace_path": str(tmp_path),
            },
            workspace=tmp_path,
            on_stream=stream_deltas.append,
        )
    finally:
        service.shutdown()

    assert result["error"] is None
    # The UI-visible side: the recovery-round answer never streamed (its deltas
    # could have duplicated the interrupted attempt on screen), and the repair-
    # round answer did — the old latch silenced incremental output for the rest
    # of the task after a single transient hiccup.
    assert "".join(stream_deltas) == "修复行内容", f"deltas: {stream_deltas}"
    # Structural latch check: provider #0 (initial attempt) launched streaming
    # turns; the recovery attempt ran atomically.
    own = [(i, s) for i, s in chat_streaming if i == 0]
    assert own == [(0, True), (0, True)], f"initial provider did not stream: {chat_streaming}"
    # The repair-round answer (the turn after the recovery completed) streamed
    # to the UI; the recovery answer never did — the interrupted attempt had
    # already published deltas, so replaying them would duplicate text on
    # screen. The flags agree, but the delivered deltas are the guarantee.
    assert "恢复行内容" not in "".join(stream_deltas)
    assert result["metrics"]["provider_recoveries"] == 1
