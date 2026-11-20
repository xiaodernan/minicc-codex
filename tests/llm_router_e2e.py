"""Manual E2E for M8-T1267's LLM transition router against the real gateway.

Runs ``choose_transition`` against the live model through the operator's Clash
lane. Never in CI (it spends real tokens). Usage::

    .venv/Scripts/python.exe tests/llm_router_e2e.py

The state is a synthetic "verify failed, repair evidence present" snapshot and
the legal edges are ``repair`` / ``summarize``: the correct model answer is
``repair``. A hallucinated or unparsable answer is rejected by fail-closed, so
the assertion also proves the safety property in the wild.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from minicc.agent.llm_router import choose_transition, parse_decision  # noqa: E402
from minicc.config import load_config  # noqa: E402
from minicc.llm.base import system_msg, user_msg  # noqa: E402
from minicc.llm.openai_provider import OpenAICompatibleProvider  # noqa: E402


async def main() -> int:
    config = load_config(workspace=ROOT)
    provider = OpenAICompatibleProvider(
        config.base_url, config.api_key, config.model,
        timeout=config.timeout,
        reasoning_effort=config.reasoning_effort,
    )
    print(f"model={config.model}  base={config.base_url}")

    state = type("S", (), {
        "phase": "verify",
        "status": "failed",
        "errors": ["pytest: 3 failed in test_payment.py — assertions on refund amount"],
        "outputs": {"verify": {"status": "failed", "summary": "3 failures, all in refund logic"},
                    "inspect": {"status": "ok", "summary": "refund() reads tier from a stale cache"}},
        "evidence": [{"ref": "test_payment.py:88"}],
        "prompt": "修复退款金额断言失败",
    })()

    async def call_model(system: str, user: str) -> str:
        response = await provider.chat(
            messages=[system_msg(system), user_msg(user)],
            tools=None, on_delta=None,
        )
        return response.text

    decision = await choose_transition(
        state=state,
        candidates=["repair", "summarize"],
        static_target="summarize",
        call_model=call_model,
        reason="节点 verify 返回 failed，需决定是修复还是收尾",
    )
    print("decision:", decision.to_dict())

    if not decision.accepted:
        print("RESULT: FAIL-LOSED (model answer rejected; static route survives)")
        return 1
    if decision.target != "repair":
        print(f"RESULT: UNEXPECTED target={decision.target!r} (expected repair)")
        return 1
    print(f"RESULT: PASS — LLM routed verify -> {decision.target}: {decision.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
