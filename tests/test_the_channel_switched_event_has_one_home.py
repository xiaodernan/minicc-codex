"""M8-T482 — 通道切换事件两个家：两个网关 provider 各手拼一份完整 trace_event

402（或带 credit 标识的 429）意味着付费通道的额度池空了：配了套餐通道时，
provider 在任务中途切换，并用同一个事件把切换说出口。两个网关 provider
（anthropic / openai-compatible）曾各自手拼这整条事件——code 与 summary 逐
字重复。一处忘了改文案，界面就用上个季度的措辞解释这次切换；一处的 code
漂移，任务事件流里就再也找不到这次切换。

家安在 `minicc/llm/usage.py`：那里本来就住着 `channel_counter` 与
`channel_status_payload` 这两个同族的通道事实。整个事件（信封五字段 +
detail 的 from/to）由 `channel_switched_event()` 一个函数产出，只有
`error_type` 是 OpenAI 那条线独有的载荷——它的裁决来自异常，类名随行。
detail 的键序保持两个调用点原本的形状，任何读者看到的载荷不变。
"""

from __future__ import annotations

import ast
import types
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/llm/usage.py"
CODE = "provider_channel_switched"
SUMMARY = "主通道额度已用尽（402/Credit 上限），本次任务改用 Step Plan 套餐通道"


def test_the_home_owns_the_event_vocabulary() -> None:
    """usage.py owns the switch event's machine name and its sentence."""
    from minicc.llm.usage import CHANNEL_SWITCHED_CODE, CHANNEL_SWITCHED_SUMMARY

    assert CHANNEL_SWITCHED_CODE == CODE
    assert CHANNEL_SWITCHED_SUMMARY == SUMMARY


def test_the_home_builds_the_whole_event() -> None:
    """The home emits the exact event both providers used to spell by hand."""
    from minicc.llm.usage import channel_switched_event

    assert channel_switched_event(402) == {
        "kind": "trace",
        "name": "provider",
        "status": "ok",
        "phase": "planning",
        "code": CODE,
        "summary": SUMMARY,
        "detail": {"from": "paid", "to": "plan", "status_code": 402},
    }


def test_the_error_type_slot_is_the_openai_wires_only_extra() -> None:
    """error_type rides along only when given, in the slot readers expect."""
    from minicc.llm.usage import channel_switched_event

    without = channel_switched_event(429)
    assert "error_type" not in without["detail"]
    with_type = channel_switched_event(429, "RateLimitError")
    assert list(with_type["detail"]) == ["from", "to", "error_type", "status_code"]
    assert with_type["detail"]["error_type"] == "RateLimitError"
    assert with_type["detail"]["status_code"] == 429


def test_no_other_module_spells_the_event_inline() -> None:
    """No module spells the code or the sentence outside the one declaration."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value in (CODE, SUMMARY):
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 2 and all(item.startswith(HOME) for item in offenders), (
        "the channel-switch event vocabulary is spelled inline outside its one home: "
        + ", ".join(offenders)
    )


def test_both_providers_consume_the_same_home_object() -> None:
    """Both gateway providers ask the home, not a copy of it."""
    from minicc.llm import anthropic_provider, openai_provider, usage

    assert anthropic_provider.channel_switched_event is usage.channel_switched_event
    assert openai_provider.channel_switched_event is usage.channel_switched_event


def test_the_anthropic_switch_emits_the_home_event() -> None:
    """The anthropic switch path emits exactly the home-built event."""
    from minicc.llm.anthropic_provider import AnthropicProvider
    from minicc.llm.usage import channel_switched_event

    events: list[dict] = []
    provider = AnthropicProvider(
        api_key="test-key",
        model="claude-test",
        base_url="https://api.stepfun.com/v1",
        plan_base_url="https://api.stepfun.com/step_plan/v1",
        max_retries=0,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})),
    )
    provider.on_status = events.append
    provider._switch_to_plan(402)
    assert events == [channel_switched_event(402)]


def test_the_openai_switch_emits_the_home_event() -> None:
    """The openai-compatible switch path emits exactly the home-built event."""
    from minicc.llm.openai_provider import OpenAICompatibleProvider
    from minicc.llm.usage import channel_switched_event

    events: list[dict] = []
    provider = OpenAICompatibleProvider(
        "https://gateway.test/v1", "test-key", "test-model",
        max_retries=0, sdk_client=types.SimpleNamespace(),
    )
    provider._on_status = events.append

    class _Quota(Exception):
        status_code = 402

    provider._emit_channel_switch(_Quota("balance exhausted"))
    assert events == [channel_switched_event(402, "_Quota")]
