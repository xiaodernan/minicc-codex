"""M8-T61: 信封模式下非 JSON 工具格式进协议修复，不再被静默当答案。

真网关实测（step-3.7-flash，envelope 模式）：模型第一轮输出 <tool_call>
XML 而非约定的 JSON 信封——修复前 provider 不解析、循环把这段 XML 当
最终答案交付，任务 4 轮零工具调用到完成评审上限。修复后抛
EnvelopeParseError（带模型原输出作纠错上下文），接入既有 protocol_repair
路径：修好后收敛，修不好则诚实地以「LLM 工具协议连续无效」失败。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from minicc.llm.envelope import EnvelopeParseError
from minicc.llm.openai_provider import OpenAICompatibleProvider


def _envelope_provider(content_by_call: list[str]):
    calls = {"n": 0}

    class Completions:
        async def create(self, **_kwargs):
            content = content_by_call[min(calls["n"], len(content_by_call) - 1)]
            calls["n"] += 1
            return SimpleNamespace(
                choices=[SimpleNamespace(
                    message=SimpleNamespace(content=content, tool_calls=[]),
                    finish_reason="stop",
                )],
                usage=None,
                model="test-model",
            )

    provider = OpenAICompatibleProvider(
        "https://example.test/v1", "test-key", "test-model",
        protocol="chat_completions", tool_mode="envelope", max_retries=0,
        sdk_client=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
    )
    provider._calls = calls
    return provider


def test_foreign_tool_call_format_raises_for_repair() -> None:
    provider = _envelope_provider([
        '<tool_call>\n<function=read_file>\n<parameter=path>notes.txt</parameter>\n</function>\n</tool_call>',
    ])
    import asyncio

    async def run():
        await provider.chat(
            [{"role": "user", "content": "读 notes.txt"}],
            tools=[{"type": "function", "function": {"name": "read_file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}}],
        )

    with pytest.raises(EnvelopeParseError) as exc_info:
        asyncio.run(run())
    # 模型自己的输出必须随异常带给协议修复路径作纠错上下文。
    assert "<tool_call>" in exc_info.value.content


def test_plain_text_answer_still_delivered(tmp_path=None) -> None:
    """没有工具调用意图的纯文本答案不得被误伤——回退只看外格式标记。"""
    provider = _envelope_provider(["任务完成：目标文件已核对，无需修改。"])
    import asyncio

    async def run():
        return await provider.chat(
            [{"role": "user", "content": "检查完成了吗"}],
            tools=[{"type": "function", "function": {"name": "read_file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}}],
        )

    response = asyncio.run(run())
    assert "任务完成" in response.content


def test_valid_envelope_still_lifts_to_tool_calls() -> None:
    provider = _envelope_provider([
        '```json\n{"action": "read_file", "params": {"path": "notes.txt"}}\n```',
    ])
    import asyncio

    async def run():
        return await provider.chat(
            [{"role": "user", "content": "读 notes.txt"}],
            tools=[{"type": "function", "function": {"name": "read_file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}}],
        )

    response = asyncio.run(run())
    assert response.tool_calls and response.tool_calls[0]["function"]["name"] == "read_file"


def test_truncated_digest_prefix_gets_a_pointing_hint(tmp_path: Path) -> None:
    """M8-T61b: 模型传 8 位截断 digest（恰为当前值前缀）时，错误必须点名截断。

    真网关实测（responses+envelope 组合）：模型从 64 位摘要只抄前 8 位 →
    通用「不匹配」消息让它反复重试同一截断值直到停滞守卫判死。点名式
    消息让下一次重试直接复制完整值。
    """
    from minicc.tools.editor import Editor, StaleContextError

    editor = Editor(tmp_path)
    editor.write_file("note.txt", "v1" + chr(10))
    full = editor.file_digest("note.txt")
    with pytest.raises(StaleContextError) as exc_info:
        editor.write_file("note.txt", "v2" + chr(10), expected_digest=full[:8])
    assert "8 位截断" in str(exc_info.value)
    assert "完整 64 位" in str(exc_info.value)
    # 文件未被改动。
    assert editor.file_digest("note.txt") == full
