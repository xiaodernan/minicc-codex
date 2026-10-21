"""M8-T342 — 「没有产出」要问工具自己的话，不要问它读回来的内容

停滞守卫用一条文本启发式判断"这一轮没有产出"：结果里出现
「无匹配 / 命中 0 / 扫描 0 文件 / 窗口为空 / 窗口越界 / duplicate_tool_call /
重复调用 / recovery_guard」就算没有产出。

但它匹配的是 **summary + head + tail**——head/tail 是**工具读回来的内容**。
于是：

* 一次**成功**的读取，只要文件正文里出现「命中 0」（本仓库的 ROADMAP 里
  到处都是），这一轮就被判成"没有产出"；
* 两次之后，停滞守卫开火：明明在干活的轮次被当成原地打转，agent 被推进
  恢复诊断，白白烧掉一轮。

而所有**有意义**的标记其实都在工具自己的 `summary` 里：

* grep 无命中 → summary "grep 'x' 扫描 N 文件命中 0 处"；
* glob 无命中 → summary "glob 'x' 命中 0 个"；
* 重复调用 → summary "[DUPLICATE_TOOL_CALL] …"；
* 恢复暂缓 → summary "[RECOVERY_GUARD] …"；
* 「窗口为空/越界」根本不是 ok 结果——read_file 抛的是 ToolError，
  status="error" 已经被判成没有产出。

本门钉住：判据只问 summary；读回的内容里出现那些字样**不算**没有产出；
真的空结果仍然算。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from minicc.agent.loop import _is_unproductive_result, run_agent
from minicc.llm.base import LLMResponse
from minicc.tools import build_registry
from minicc.tools.editor import Editor
from minicc.tools.schemas import ToolResult


def test_content_that_mentions_a_zero_hit_is_not_unproductive() -> None:
    """The defect: a successful read is judged by the text it read."""
    result = ToolResult(
        status="ok",
        summary="读取 notes.txt (行 1-2, digest abc…)",
        head="命中 0 处；无匹配",
        tail="",
    )
    assert _is_unproductive_result(result) is False, result


def test_a_real_empty_grep_is_unproductive() -> None:
    """The control: the tool's own summary still says it."""
    result = ToolResult(
        status="ok",
        summary="grep 'needle' 扫描 12 文件命中 0 处",
        head="(无匹配)",
        tail="",
    )
    assert _is_unproductive_result(result) is True, result


def test_the_duplicate_and_guard_summaries_still_count() -> None:
    duplicate = ToolResult(status="ok", summary="[DUPLICATE_TOOL_CALL] 已复用 read_file 的最近一次成功结果")
    guard = ToolResult(status="denied", summary="[RECOVERY_GUARD] 已暂缓写入")
    assert _is_unproductive_result(duplicate) is True, duplicate
    assert _is_unproductive_result(guard) is True, guard


def test_an_error_result_is_unproductive() -> None:
    error = ToolResult(status="error", summary="读取窗口为空或越界: notes.txt")
    assert _is_unproductive_result(error) is True, error


def test_reading_a_document_that_says_zero_hits_does_not_stall_the_run(
    tmp_path: Path,
) -> None:
    """The observable site: the stagnation guard must not fire on real work."""
    (tmp_path / "notes.md").write_text(
        "这一行说：命中 0 处\n另一行：无匹配\n",
        encoding="utf-8",
    )

    class _Provider:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, tools=None, on_delta=None, **kwargs):
            self.calls += 1
            if self.calls <= 2:
                return LLMResponse(
                    tool_calls=[{
                        "id": f"read-{self.calls}",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": json.dumps({"path": "notes.md"})},
                    }],
                    finish_reason="tool_calls",
                )
            return LLMResponse(content="done", finish_reason="stop")

    traces: list[dict[str, Any]] = []
    asyncio.run(run_agent(
        _Provider(),
        build_registry(Editor(tmp_path)),
        [{"role": "user", "content": "读一下笔记"}],
        max_turns=6,
        on_trace=traces.append,
        should_allow=lambda _name, _call: True,
        workspace=tmp_path,
    ))
    codes = {str(event.get("code") or "") for event in traces}
    # The damage of a false "unproductive" verdict: the stagnation path opens
    # (the round is called a repetition) and the agent is pushed into the
    # recovery probe, from where it can only churn.
    assert "stagnation_replan" not in codes, sorted(codes)
    assert "recovery_probe_finished" not in codes, sorted(codes)
