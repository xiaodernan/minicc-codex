"""M8-T1015: the completion judge's two system layers are the cache contract.

Every real-API measurement kept one constant in view: the completion judge is
an atomic (non-stream) call whose persona used to be ~300 tokens of prefix -
below the gateway's cache threshold, so every ``completion_judge`` turn paid
full price.  This suite pins the new shape:

* the reviewer wire is ``system(persona)`` → ``system(protocol)`` → ``user(packet)``,
* ``COMPLETION_REVIEW_PROTOCOL`` is byte-constant (no f-string placeholders),
* the unique evidence packet no longer duplicates the example JSON.
"""

from __future__ import annotations

import asyncio
import json

from minicc.agent.completion import (
    COMPLETION_REVIEW_PROTOCOL,
    COMPLETION_REVIEW_SYSTEM,
    build_completion_review_prompt,
    judge_completion,
)
from minicc.llm.base import LLMResponse


def test_protocol_layer_is_a_stable_constant() -> None:
    assert len(COMPLETION_REVIEW_PROTOCOL) >= 500
    # it is a plain literal: an f-string would have raised at import time if a
    # placeholder were left unformatted, and runtime formatting would smuggle in
    # per-call bytes - so rule them out explicitly.
    assert "{task}" not in COMPLETION_REVIEW_PROTOCOL
    assert "{answer}" not in COMPLETION_REVIEW_PROTOCOL
    assert "{workspace}" not in COMPLETION_REVIEW_PROTOCOL
    for key in (
        "status",
        "confidence",
        "rationale",
        "missing",
        "next_action",
        "evidence",
    ):
        assert key in COMPLETION_REVIEW_PROTOCOL


def test_the_user_packet_no_longer_duplicates_the_example() -> None:
    prompt = build_completion_review_prompt(
        task="fix the parser",
        answer="done",
        events=[],
        verification_results=[],
        allow_changes=True,
        workspace="ws",
    )
    assert "请严格返回 JSON，例如" not in prompt
    assert "证据包协议" in COMPLETION_REVIEW_PROTOCOL
    assert "证据包协议" in prompt, "packet must still point at the protocol section by name"


def test_judge_sends_persona_then_protocol_then_packet() -> None:
    recorded: dict[str, object] = {}

    class Provider:
        async def chat(self, **kwargs):
            recorded["messages"] = kwargs.get("messages") or []
            return LLMResponse(
                content=json.dumps({
                    "status": "blocked",
                    "confidence": 0.1,
                    "rationale": "no evidence to review",
                    "missing": [],
                    "next_action": None,
                    "evidence": [],
                })
            )

    asyncio.run(
        judge_completion(
            Provider(),
            task="fix the parser",
            answer="done",
            events=[],
            verification_results=[],
            allow_changes=True,
            workspace="ws",
        )
    )
    messages = recorded["messages"]
    assert isinstance(messages, list)
    roles = [m.get("role") for m in messages]
    assert roles == ["system", "system", "user"], roles
    assert messages[0]["content"] == COMPLETION_REVIEW_SYSTEM
    assert messages[1]["content"] == COMPLETION_REVIEW_PROTOCOL
    assert "原始用户需求" in messages[2]["content"]


def test_two_calls_share_the_prefix_byte_for_byte() -> None:
    first = [m for m in _recorded_messages("fix the parser")]
    second = [m for m in _recorded_messages("rename the module")]
    assert [m["content"] for m in first[:2]] == [m["content"] for m in second[:2]]
    assert first[2]["content"] != second[2]["content"]


def _recorded_messages(task: str):
    recorded: dict[str, object] = {}

    class Provider:
        async def chat(self, **kwargs):
            recorded["messages"] = kwargs.get("messages") or []
            return LLMResponse(
                content=json.dumps({
                    "status": "blocked",
                    "confidence": 0.1,
                    "rationale": "r",
                    "missing": [],
                    "next_action": None,
                    "evidence": [],
                })
            )

    asyncio.run(
        judge_completion(
            Provider(),
            task=task,
            answer="done",
            events=[],
            verification_results=[],
            allow_changes=True,
            workspace="ws",
        )
    )
    return recorded["messages"]
