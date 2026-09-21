"""Deterministic in-process provider for tests and Playwright smoke.

Never contacts the network. Activated by ``MINICC_FAKE_PROVIDER=1`` or the
worker ``--fake-provider`` flag. The contract matches the duck-typed
provider used by ``run_agent`` / ``AgentService.make_provider``.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .base import LLMResponse


# M4-T4: deterministic per-turn usage so the cost pipeline (pricing.cost_usd →
# tokens_used → benchmark cost_per_success_usd) is observable without a real
# model. Split into prompt/completion so cache-discount math has something to
# bite on; totals are the sum of their parts.
_FAKE_USAGE: dict[str, dict[str, int]] = {
    "tool": {"prompt_tokens": 120, "completion_tokens": 20, "total_tokens": 140},
    "answer": {"prompt_tokens": 150, "completion_tokens": 30, "total_tokens": 180},
    "judge": {"prompt_tokens": 200, "completion_tokens": 25, "total_tokens": 225},
}


class FakeProvider:
    """One-shot assistant reply; planner/judge calls get a complete JSON."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._turn = 0
        self._agent_turn = 0

    async def chat(self, messages, tools, on_delta=None):
        self._turn += 1
        if tools is None:
            # Completion tests exercise the real evidence-reference contract.
            # M4-T1: the judge rejects a completion that cites only trace ids,
            # so pick an id that is actually citable (a write, a verification,
            # an error, or a real tool observation) instead of the last id.
            references = self._select_citable_evidence(messages)
            decision = json.dumps(
                {
                    "status": "complete" if references else "unknown",
                    "confidence": 0.9,
                    "rationale": "fake provider",
                    "missing": [],
                    "next_action": "",
                    "evidence": references,
                },
                ensure_ascii=False,
            )
            return LLMResponse(content=decision, usage=_FAKE_USAGE["judge"])
        self._agent_turn += 1
        if self._agent_turn == 1:
            # M4-T1: a zero-write readonly task still needs at least one
            # citable tool observation, otherwise the completion judge has
            # nothing but trace ids and must refuse to converge. Emit one
            # safe readonly call before the final answer.
            return LLMResponse(
                content="",
                tool_calls=[
                    {
                        "id": "fake-read-1",
                        "type": "function",
                        "function": {"name": "tree", "arguments": "{}"},
                    }
                ],
                finish_reason="tool_calls",
                usage=_FAKE_USAGE["tool"],
            )
        text = "fake-provider-answer"
        if on_delta is not None:
            on_delta(text)
        return LLMResponse(content=text, usage=_FAKE_USAGE["answer"])

    @staticmethod
    def _select_citable_evidence(messages) -> list[str]:
        """Return one evidence id the completion judge is allowed to cite."""

        marker = "执行证据（工具调用、阶段 trace、修改和验证结果）：\n"
        prompt_text = ""
        for message in messages if isinstance(messages, list) else []:
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, str) and marker in content:
                prompt_text = content
                break
        if prompt_text:
            start = prompt_text.find(marker)
            rest = prompt_text[start + len(marker):]
            end = rest.find("\n\n请严格返回 JSON")
            packet_text = rest[:end] if end >= 0 else rest
            try:
                packet = json.loads(packet_text)
            except (json.JSONDecodeError, TypeError):
                packet = {}
            if isinstance(packet, dict):
                for item in packet.get("verification_results", []):
                    if isinstance(item, dict) and item.get("id"):
                        return [str(item["id"])]
                for item in packet.get("events", []):
                    if not isinstance(item, dict):
                        continue
                    kind = item.get("kind")
                    name = item.get("name")
                    citable = (
                        item.get("write")
                        or kind == "verification"
                        or item.get("status") == "error"
                        or (kind != "trace" and name and name != "agent")
                    )
                    if citable and item.get("id"):
                        return [str(item["id"])]
        # Fallback: any packet id at all (older prompts / parse misses).
        found = re.findall(
            r'"id"\s*:\s*"((?:event|verification)-\d+)"',
            json.dumps(messages, ensure_ascii=False).replace('\\"', '"'),
        )
        return found[-1:]

    async def close(self) -> None:
        return None

    def protocol(self) -> str:
        return "fake"

    def protocol_status(self) -> dict[str, Any]:
        return {"requested": "auto", "active": "fake"}

    @staticmethod
    def is_transient_failure(value: BaseException | str) -> bool:
        return False


__all__ = ["FakeProvider"]
