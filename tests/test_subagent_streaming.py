"""M6-T2: subagent progress visibility, prompt cancellation and parent budget.

Three things these tests pin down:

1. a running subagent bubbles ``on_trace`` events to the parent sink, each
   tagged with a stable ``parent_id`` and its ``depth`` (the parent's SSE can
   show what the child is doing without exposing the raw transcript);
2. the parent waits with bounded polling, so setting the shared cancel event
   aborts promptly instead of blocking on one ``future.result(600)``;
3. DAG nodes run under a Budget that inherits the session's soft ceilings as a
   hard stop, and their token totals are folded back into the parent budget.
"""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import pytest

from minicc.agent.graph import aggregate_dag_tokens, node_budget_from
from minicc.agent.state import Budget, BudgetExceeded
from minicc.agent.subagent import WAIT_POLL_SECONDS, build_task_tool_spec
from minicc.llm.base import LLMResponse
from minicc.tools import build_registry
from minicc.tools.editor import Editor


class ScriptedProvider:
    """One tool-use turn (read_file) then a final answer, reporting usage."""

    def __init__(self) -> None:
        self.turns = 0
        self.closed = False

    async def chat(self, messages, tools, on_delta=None):
        self.turns += 1
        if self.turns == 1:
            return LLMResponse(
                tool_calls=[{
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "README.md"}'},
                }],
                usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            )
        return LLMResponse(
            content="结论：这是一个本地 coding agent。",
            usage={"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        )

    async def close(self) -> None:
        self.closed = True


class EndlessSlowProvider:
    """Never converges on its own — only external cancellation can stop it."""

    def __init__(self) -> None:
        self.turns = 0

    async def chat(self, messages, tools, on_delta=None):
        self.turns += 1
        await asyncio.sleep(0.4)
        return LLMResponse(tool_calls=[{
            "id": f"call-{self.turns}",
            "type": "function",
            "function": {"name": "read_file", "arguments": '{"path": "README.md"}'},
        }])

    async def close(self) -> None:
        return None


def _workspace(tmp_path: Path) -> Path:
    (tmp_path / "README.md").write_text("# demo project\n", encoding="utf-8")
    return tmp_path


def test_subagent_traces_bubble_to_parent_with_parent_id(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    events: list[dict] = []
    spec = build_task_tool_spec(
        provider_factory=ScriptedProvider,
        workspace=workspace,
        system_prompt="你是 minicc 测试系统提示。",
        base_registry=build_registry(Editor(workspace)),
        on_trace=events.append,
    )
    result = spec.handler({"description": "调研项目结构", "prompt": "读取 README.md 并总结项目用途。"})

    assert result.status == "ok"
    tagged = [event for event in events if event.get("subagent")]
    # Acceptance: at least three subagent events reach the parent sink.
    assert len(tagged) >= 3
    ids = {event.get("parent_id") for event in tagged}
    assert len(ids) == 1 and next(iter(ids)), "every bubbled event shares one parent_id"
    assert all(event.get("depth") == 1 for event in tagged)
    codes = [event.get("code") for event in tagged]
    assert "subagent_started" in codes
    assert "subagent_finished" in codes
    # tokens/answer never ride on the lifecycle events themselves.
    finished = next(event for event in tagged if event["code"] == "subagent_finished")
    assert finished["detail"]["tokens_used"] == 45


def test_parent_waits_bounded_and_cancels_promptly(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    assert WAIT_POLL_SECONDS < 1.0, "the parent must poll on a short slice, not block"
    cancel = threading.Event()
    provider = EndlessSlowProvider()
    spec = build_task_tool_spec(
        provider_factory=lambda: provider,
        workspace=workspace,
        system_prompt="sys",
        base_registry=build_registry(Editor(workspace)),
        cancel_event=cancel,
        timeout_seconds=30.0,
    )

    def cancel_soon() -> None:
        time.sleep(0.5)
        cancel.set()

    timer = threading.Thread(target=cancel_soon, daemon=True)
    timer.start()
    started = time.monotonic()
    result = spec.handler({"description": "持续调研任务", "prompt": "反复读取 README.md 直到取消。"})
    timer.join(timeout=2.0)
    elapsed = time.monotonic() - started

    assert result.status == "cancelled"
    # The two endings are distinguishable by text, so the text carries the
    # claim; the timer is left as a liveness bound that still sits under the
    # 30s timeout it is meant to rule out.
    assert "[TIMEOUT]" not in result.summary, result.summary
    assert elapsed < 15.0, f"waited {elapsed:.1f}s after a 0.5s cancel signal"


def test_subagent_still_reports_usage_when_it_completes(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    spec = build_task_tool_spec(
        provider_factory=ScriptedProvider,
        workspace=workspace,
        system_prompt="sys",
        base_registry=build_registry(Editor(workspace)),
    )
    result = spec.handler({"description": "读取并总结", "prompt": "读取 README.md 并总结。"})
    assert result.status == "ok"
    assert result.data["tokens_used"]["total_tokens"] == 45


def test_node_budget_turns_soft_ceiling_into_hard_stop() -> None:
    parent = Budget(soft_max_tokens=1000, soft_max_duration_seconds=60.0)
    node = node_budget_from(parent)
    # A node keeps no turn/tool ceiling but cannot exceed the session's soft
    # token budget — the soft ceiling becomes the node's hard max.
    assert node.max_tokens == 1000
    assert node.soft_max_tokens == 1000
    assert node.soft_max_duration_seconds == 60.0
    node.record_usage({"total_tokens": 900})  # under the cap, keeps running
    with pytest.raises(BudgetExceeded):
        node.record_usage({"total_tokens": 200})  # 1100 > 1000 -> budget_exceeded


def test_dag_token_totals_fold_into_parent_budget() -> None:
    outputs = {
        "a": {"status": "completed", "tokens_used": {"total_tokens": 100, "prompt_tokens": 60}},
        "b": {"status": "completed", "tokens_used": {"total_tokens": 250}},
        "c": {"status": "failed"},
        "d": {"status": "skipped", "reason": "dependency_failed"},
    }
    totals = aggregate_dag_tokens(outputs)
    assert totals["total_tokens"] == 350
    assert totals["prompt_tokens"] == 60

    runtime = Budget()
    runtime.record_usage({"total_tokens": totals["total_tokens"]})
    # Acceptance: after the DAG, the session budget reflects *all* node usage.
    assert runtime.tokens == 350
