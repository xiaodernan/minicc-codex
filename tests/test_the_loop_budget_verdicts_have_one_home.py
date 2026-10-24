"""M8-T501 — loop 预算判词四个家：两条超时出口、两个软预算停机点

「最大执行时间已用尽，已取消当前模型请求」在 `chat_with_cancellation`
里有两个家（`wait_for` 竞态出口、deadline 任务出口）；「软预算收束轮次后
仍超限，已停止」在 `run_agent` 里有两个家（wrap 轮又调工具的停机点、wrap
轮直接回答的停机点）。两条判词各被手拼两遍——一处改了措词其余没跟上，
审计事件和异常消息读到的是不同的事实，没有任何测试会红。

家安在 `minicc/agent/loop.py` 模块层，紧挨 `chat_with_cancellation`——第
一条判词的调用点都在它里面，第二条在同一个模块的 `run_agent`。
"""

from __future__ import annotations

import ast
import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/agent/loop.py"
MAX_DURATION = "最大执行时间已用尽，已取消当前模型请求"
SOFT_BUDGET_STOPPED = "软预算收束轮次后仍超限，已停止"


def _literal_shapes():
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        inside_fstring: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                for child in ast.iter_child_nodes(node):
                    inside_fstring.add(id(child))
        for node in ast.walk(tree):
            if id(node) in inside_fstring:
                continue
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                yield path, node.lineno, node.value
            elif isinstance(node, ast.JoinedStr):
                parts = [
                    part.value
                    for part in node.values
                    if isinstance(part, ast.Constant) and isinstance(part.value, str)
                ]
                yield path, node.lineno, "".join(parts)


def _sites_of(sentence: str) -> list[str]:
    return [
        f"{path.relative_to(REPO).as_posix()}:{lineno}"
        for path, lineno, text in _literal_shapes()
        if text == sentence
    ]


def _one_home(sentence: str) -> None:
    offenders = _sites_of(sentence)
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        f"the sentence {sentence!r} is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )


def test_the_max_duration_home_pins_the_sentence() -> None:
    from minicc.agent.loop import max_duration_exhausted_message

    assert max_duration_exhausted_message() == MAX_DURATION


def test_the_soft_budget_home_pins_the_sentence() -> None:
    from minicc.agent.loop import soft_budget_stopped_summary

    assert soft_budget_stopped_summary() == SOFT_BUDGET_STOPPED


def test_the_max_duration_sentence_is_spelled_exactly_once() -> None:
    _one_home(MAX_DURATION)


def test_the_soft_budget_sentence_is_spelled_exactly_once() -> None:
    _one_home(SOFT_BUDGET_STOPPED)


def test_every_home_is_asked_by_every_site() -> None:
    source = (REPO / HOME).read_text(encoding="utf-8")
    for name in (
        "max_duration_exhausted_message(",
        "soft_budget_stopped_summary(",
    ):
        assert source.count(name) == 3, (
            f"loop.py asks {name} {source.count(name)} times, expected 3 "
            "(one definition plus two call sites)"
        )


# --- one behavioural assertion per exit ---------------------------------------


class _HangingProvider:
    async def chat(self, messages, tools, on_delta=None):
        await asyncio.sleep(30)

    async def close(self) -> None:
        return None


def test_the_wait_for_exit_emits_the_homes_sentence() -> None:
    from minicc.agent.loop import BudgetExceeded, chat_with_cancellation

    async def scenario():
        return await chat_with_cancellation(
            _HangingProvider(),
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            on_delta=None,
            cancel_event=None,
            timeout_seconds=0.05,
        )

    with pytest.raises(BudgetExceeded) as excinfo:
        asyncio.run(scenario())
    assert str(excinfo.value) == MAX_DURATION, excinfo.value


def test_the_deadline_exit_emits_the_homes_sentence() -> None:
    from minicc.agent.loop import BudgetExceeded, chat_with_cancellation

    async def scenario():
        return await chat_with_cancellation(
            _HangingProvider(),
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            on_delta=None,
            cancel_event=threading.Event(),
            timeout_seconds=0.05,
        )

    with pytest.raises(BudgetExceeded) as excinfo:
        asyncio.run(scenario())
    assert str(excinfo.value) == MAX_DURATION, excinfo.value


def _run_loop(tmp_path: Path, provider, events: list[dict]):
    from minicc.agent.loop import run_agent
    from minicc.agent.state import Budget

    async def scenario():
        return await run_agent(
            provider,
            _registry(tmp_path),
            [{"role": "user", "content": "读 README"}],
            budget=Budget(soft_max_duration_seconds=0.0),
            on_trace=events.append,
        )

    return asyncio.run(scenario())


def _registry(tmp_path: Path):
    from minicc.tools import build_registry
    from minicc.tools.editor import Editor

    return build_registry(Editor(tmp_path))


class _ToolThenProvider:
    """First turn calls a tool; the wrap-up round never gets a second chat."""

    async def chat(self, messages, tools, on_delta=None):
        from minicc.llm.base import LLMResponse

        return LLMResponse(
            tool_calls=[{
                "id": "call-1",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path": "README.md"}'},
            }],
        )

    async def close(self) -> None:
        return None


class _TextProvider:
    async def chat(self, messages, tools, on_delta=None):
        from minicc.llm.base import LLMResponse

        return LLMResponse(content="收束结论")

    async def close(self) -> None:
        return None


def test_the_wrap_up_tool_round_stop_emits_the_homes_sentence(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    events: list[dict] = []
    result = _run_loop(tmp_path, _ToolThenProvider(), events)
    assert any(
        event.get("summary") == SOFT_BUDGET_STOPPED for event in events
    ), events


def test_the_wrap_up_text_round_stop_emits_the_homes_sentence(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    events: list[dict] = []
    result = _run_loop(tmp_path, _TextProvider(), events)
    assert any(
        event.get("summary") == SOFT_BUDGET_STOPPED for event in events
    ), events
    assert result.answer == "收束结论", result.answer
