"""M8-T284: two parallel subagents must not share one run's bookkeeping.

The runner is shared by every ``task`` call of a session, and the model may
fire several in parallel ("investigate A and B in parallel").  The per-run
state - the child's own usage payload, the fallback budget, the run id -
lived on the runner instance, so the second call reset the first call's
payload to ``None``.  The first call then folded **nothing** to the parent,
and the parent budget was undercounted - which is how a fan-out escapes its
own ceiling.  ``_run_id`` had the same problem: a grandchild's traces were
filed under whichever sibling started last.

The state is now per thread, so parallel calls cannot see each other.

This door pins:

* two parallel runs each fold their own usage - two reports, not one;
* the control: a single run folds its usage exactly once.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any

from minicc.agent.subagent import build_task_tool_spec
from minicc.llm.base import LLMResponse
from minicc.tools import build_registry
from minicc.tools.editor import Editor


class _Provider:
    """Answers after a short delay, so two calls really overlap."""

    def __init__(self, delay: float) -> None:
        self.delay = delay

    async def chat(self, messages, tools=None, on_delta=None, **kwargs):
        await asyncio.sleep(self.delay)
        return LLMResponse(
            content="子代理结论：已完成。",
            finish_reason="stop",
            usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        )

    async def close(self) -> None:
        return None


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("# demo\n", encoding="utf-8")
    return workspace


def _build(workspace: Path, on_child_usage: Any) -> Any:
    return build_task_tool_spec(
        provider_factory=lambda: _Provider(0.15),
        workspace=workspace,
        system_prompt="你是 minicc 测试系统提示。",
        base_registry=build_registry(Editor(workspace)),
        on_child_usage=on_child_usage,
    )


def test_two_parallel_runs_each_fold_their_own_usage(tmp_path: Path) -> None:
    """Two runs, two reports - the shared state produced one."""
    workspace = _workspace(tmp_path)
    reported: list[dict[str, Any]] = []
    lock = threading.Lock()

    def on_child_usage(usage: dict[str, Any]) -> None:
        with lock:
            reported.append(dict(usage))

    spec = _build(workspace, on_child_usage)

    def call(description: str) -> None:
        spec.handler({
            "description": description,
            "prompt": f"读取 README.md 并总结 {description}。",
        })

    threads = [threading.Thread(target=call, args=(f"任务 {index}",)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
        # A join with a timeout returning does not mean the thread stopped.
        assert not thread.is_alive(), "a subagent thread outlived its join"

    assert len(reported) == 2, (
        f"expected one usage report per run, got {len(reported)}: {reported}"
    )
    for payload in reported:
        assert int(payload.get("total_tokens") or 0) > 0


def test_a_run_id_belongs_to_its_own_thread(tmp_path: Path) -> None:
    """The mechanism: the run state is per thread, so siblings cannot see it.

    The behavioural test above can only catch the shared state when the
    timing lines up (one run has to reset the other's payload in the window
    between the payload being set and being folded).  This one states the
    property directly, so it is red whenever the state is shared - whatever
    the timing.
    """
    from minicc.agent.subagent import _SubagentRunner

    workspace = _workspace(tmp_path)
    runner = _SubagentRunner(
        provider_factory=lambda: _Provider(0.01),
        workspace=workspace,
        system_prompt="sys",
        base_registry=build_registry(Editor(workspace)),
        max_turns=2,
        timeout_seconds=5.0,
        cancel_event=None,
    )

    seen: dict[str, str] = {}
    started = threading.Event()
    release = threading.Event()

    def writer() -> None:
        runner._run_id = "sub-writer"
        runner._child_usage_payload = {"total_tokens": 11}
        started.set()
        release.wait(timeout=10)

    def reader() -> None:
        started.wait(timeout=10)
        seen["id"] = runner._run_id
        seen["payload"] = repr(runner._child_usage_payload)
        release.set()

    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive(), "a thread outlived its join"

    assert seen["id"] != "sub-writer", "the second thread saw the first thread's run id"
    assert seen["payload"] == "None", (
        f"the second thread saw the first thread's usage payload: {seen['payload']}"
    )


def test_a_single_run_folds_its_usage_exactly_once(tmp_path: Path) -> None:
    """The control: the ordinary path is unchanged."""
    workspace = _workspace(tmp_path)
    reported: list[dict[str, Any]] = []
    spec = _build(workspace, lambda usage: reported.append(dict(usage)))
    spec.handler({"description": "单个任务", "prompt": "读取 README.md 并总结用途。"})
    assert len(reported) == 1, f"expected exactly one usage report, got {reported}"
    assert int(reported[0].get("total_tokens") or 0) > 0
