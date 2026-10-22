"""M8-T361 — Ctrl-C 是"叫停"，不是"崩溃"：REPL 得活着回到提示符

在一轮**执行途中**按 Ctrl-C，是用户叫停一个跑飞的 agent 的常规动作 ✓。而 CLI 的
REPL 当时**没有任何兜底** ✓——`KeyboardInterrupt` 从 `_turn` 一路冲出 `_interactive`
✓（实测：`ESCAPED: KeyboardInterrupt` ✓）：整个 CLI 死掉 ✓，用户看到的是一段
traceback ✓，对话也一起没了 ✓。

Web 那边对"取消"是有正经处理的 ✓（任务落到 `interrupted` ✓、历史留下 ✓），**CLI
这一面欠对齐** ✓——被钉住的契约在 Web 那一侧 ✓，CLI 欠的那笔要还 ✓。

本门钉住：中断之后 REPL **回到提示符** ✓（第二轮照常跑 ✓、`_interactive` 正常返回
✓ 而不是抛出去 ✓）；控制组——被中断的那条请求**留在对话里** ✓（不静默丢弃 ✓），
第二轮的用户消息照常追加 ✓。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from minicc.config import Config
from minicc.llm.base import LLMResponse
from minicc.main import _interactive
from minicc.tools import build_registry
from minicc.tools.editor import Editor


class _InterruptedOnce:
    """The first turn is interrupted; the second one runs."""

    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, tools=None, on_delta=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise KeyboardInterrupt()
        return LLMResponse(content="done", finish_reason="stop")


def _config() -> Config:
    return Config(
        base_url="http://localhost:1/v1",
        api_key="k",
        model="m",
        max_turns=2,
    )


def test_the_repl_comes_back_to_the_prompt_after_an_interrupt(
    tmp_path: Path, monkeypatch
) -> None:
    prompts = iter(["做点事", "再来一次", "/exit"])
    monkeypatch.setattr("builtins.input", lambda *_: next(prompts))

    provider = _InterruptedOnce()
    messages: list[dict[str, Any]] = [{"role": "user", "content": "做点事"}]

    # The observable: the REPL returns normally instead of letting the
    # interrupt escape, and the second turn actually ran.
    try:
        asyncio.run(_interactive(
            provider,
            build_registry(Editor(tmp_path)),
            messages,
            _config(),
            stream=False,
            workspace=tmp_path,
        ))
    except KeyboardInterrupt:
        pytest.fail("the interrupt escaped the REPL: the CLI died with it")

    assert provider.calls == 2, provider.calls


def test_the_interrupted_request_stays_in_the_conversation(
    tmp_path: Path, monkeypatch
) -> None:
    prompts = iter(["做点事", "再来一次", "/exit"])
    monkeypatch.setattr("builtins.input", lambda *_: next(prompts))

    messages: list[dict[str, Any]] = [{"role": "user", "content": "做点事"}]
    try:
        asyncio.run(_interactive(
            _InterruptedOnce(),
            build_registry(Editor(tmp_path)),
            messages,
            _config(),
            stream=False,
            workspace=tmp_path,
        ))
    except KeyboardInterrupt:
        pytest.fail("the interrupt escaped the REPL: the CLI died with it")

    user_texts = [
        str(message.get("content") or "")
        for message in messages
        if message.get("role") == "user"
    ]
    # The interrupted request is not silently dropped ...
    assert "做点事" in user_texts, user_texts
    # ... and the next turn's request is appended as usual.
    assert "再来一次" in user_texts, user_texts
