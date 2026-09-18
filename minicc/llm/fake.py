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


class FakeProvider:
    """One-shot assistant reply; planner/judge calls get a complete JSON."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._turn = 0

    async def chat(self, messages, tools, on_delta=None):
        self._turn += 1
        if tools is None:
            # Completion tests exercise the real evidence-reference contract.
            # Select an ID from the supplied packet instead of inventing one.
            references = re.findall(r'"id"\s*:\s*"((?:event|verification)-\d+)"', json.dumps(messages, ensure_ascii=False).replace('\\"', '"'))
            decision = json.dumps(
                {
                    "status": "complete" if references else "unknown",
                    "confidence": 0.9,
                    "rationale": "fake provider",
                    "missing": [],
                    "next_action": "",
                    "evidence": references[-1:],
                },
                ensure_ascii=False,
            )
            return LLMResponse(content=decision)
        text = "fake-provider-answer"
        if on_delta is not None:
            on_delta(text)
        return LLMResponse(content=text)

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
