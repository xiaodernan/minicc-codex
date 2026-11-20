"""Manual E2E for M8-T1271's repair-fork decider against the real gateway.

Runs ``repair_fork_decision`` against the live model through the operator's
Clash lane. Never in CI (it spends real tokens). Usage::

    .venv/Scripts/python.exe tests/llm_repair_fork_e2e.py

Two snapshots, two honest answers:

* an actionable failure (assertion mismatch the model's own change caused) ->
  ``repair`` — today's unconditional move, now *justified*;
* a dead-environment failure (docker missing, nothing code can fix) ->
  ``summarize`` with a reason — the honest early exit the static reflex can
  never take.

Fail-closed assertions ride along: any hallucinated or unparsable answer is
rejected in the wild too.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from minicc.agent.llm_router import repair_fork_decision  # noqa: E402
from minicc.config import load_config  # noqa: E402
from minicc.llm.openai_provider import OpenAICompatibleProvider  # noqa: E402


async def main() -> int:
    config = load_config(workspace=ROOT)
    provider = OpenAICompatibleProvider(
        config.base_url, config.api_key, config.model,
        timeout=config.timeout,
        reasoning_effort=config.reasoning_effort,
    )
    print(f"model={config.model}  base={config.base_url}")

    actionable = await repair_fork_decision(
        provider,
        objective="修复 sums.py 中 add() 的整数溢出并让测试全绿",
        verification_command="python -m pytest tests/test_sums.py -q",
        verification_output=(
            "FAILED tests/test_sums.py::test_add_overflow - "
            "AssertionError: assert 2147483648 == -2147483648 : add(INT_MAX, 1) "
            "should wrap to INT_MIN but returned 2147483648"
        ),
        repair_attempts=0,
        max_repairs=2,
        evidence_count=3,
    )
    print(f"actionable  -> target={actionable.target} source={actionable.source} reason={actionable.reason}")
    assert actionable.target == "repair", f"actionable failure must route to repair, got {actionable.target}"

    environmental = await repair_fork_decision(
        provider,
        objective="更新 README 的安装说明",
        verification_command="docker compose run --rm tests",
        verification_output=(
            "docker: Cannot connect to the Docker daemon at unix:///var/run/docker.sock. "
            "Is the docker daemon running? (exit code 1; the change touched only docs/)"
        ),
        repair_attempts=1,
        max_repairs=2,
        evidence_count=2,
    )
    print(f"environmental -> target={environmental.target} source={environmental.source} reason={environmental.reason}")
    assert environmental.target == "summarize", (
        f"dead-docker failure should honestly summarize, got {environmental.target} ({environmental.reason})"
    )
    assert environmental.reason, "the summarize exit must carry a reason for the ledger"

    hallucination = await repair_fork_decision(
        provider,
        objective="x",
        verification_command="pytest",
        verification_output="boom",
        repair_attempts=0,
        max_repairs=2,
    )
    assert hallucination.target in ("repair", "summarize"), "fail-closed keeps targets legal"

    await provider.close()
    print("llm repair-fork e2e passed: real model decided both forks within the legal edge set")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
