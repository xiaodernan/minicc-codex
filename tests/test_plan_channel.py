"""双通道 provider 测试（M8-T55）：主通道额度用尽时切换到 Step Plan 套餐通道。

Step Plan（订阅 Credit 月池）与付费 API 用同一类 API Key，但 base URL 不同、
额度独立。付费通道耗尽时任务会以 402 / Credit 型 429 死掉——本文件钉住
「死掉就切换、切换是粘性的、限流不误判切换」这三条契约。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest
from openai import APIStatusError, RateLimitError

from minicc.llm.openai_provider import OpenAICompatibleProvider, _is_quota_exhausted


def _response(status: int, body: object = None) -> httpx.Response:
    return httpx.Response(
        status,
        content=b"" if body is None else json.dumps(body).encode(),
        request=httpx.Request("POST", "https://gateway.test/v1/chat/completions"),
    )


def _quota_402() -> APIStatusError:
    return APIStatusError(
        "余额不足",
        response=_response(402),
        body={"error": {"code": "insufficient_balance", "message": "余额不足"}},
    )


def _rate_limit_429(body: object | None = None) -> RateLimitError:
    return RateLimitError(
        "request limited RPM reached, current: 11, limit: 10",
        response=_response(429, body),
        body=body,
    )


def _ok_payload(channel_mark: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content=channel_mark, tool_calls=[]),
            finish_reason="stop",
        )],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        model="test-model",
    )


def _provider(paid_factory, plan_factory=None, **kwargs) -> OpenAICompatibleProvider:
    """paid_factory/plan_factory: 无参调用返回一次 create() 的结果或抛错。"""
    paid_calls = {"n": 0}

    class PaidCompletions:
        async def create(self, **_kwargs):
            paid_calls["n"] += 1
            return paid_factory(paid_calls["n"])

    clients = [SimpleNamespace(chat=SimpleNamespace(completions=PaidCompletions()))]
    if plan_factory is not None:
        plan_calls = {"n": 0}

        class PlanCompletions:
            async def create(self, **_kwargs):
                plan_calls["n"] += 1
                return plan_factory(plan_calls["n"])

        clients.append(SimpleNamespace(chat=SimpleNamespace(completions=PlanCompletions())))
    provider = OpenAICompatibleProvider(
        "https://gateway.test/v1", "test-key", "test-model",
        protocol="chat_completions", max_retries=0,
        plan_base_url="https://gateway.test/step_plan/v1" if plan_factory is not None else "",
        plan_api_key="plan-key" if plan_factory is not None else "",
        sdk_client=clients[0],
        **kwargs,
    )
    if plan_factory is not None:
        provider._plan_client = clients[1]
    provider._paid_calls = paid_calls
    return provider


def _events(provider: OpenAICompatibleProvider) -> list[dict]:
    return provider._status_events  # type: ignore[attr-defined]


def test_quota_402_switches_to_plan_channel_and_is_sticky() -> None:
    """主通道 402 → 切到套餐 → 之后每次调用直达套餐（粘性，不再试付费）。"""
    provider = _provider(
        lambda n: (_ for _ in ()).throw(_quota_402()),
        lambda n: _ok_payload("from-plan"),
    )
    events: list[dict] = []
    provider._on_status = events.append

    async def run():
        first = await provider.chat([{"role": "user", "content": "hi"}])
        second = await provider.chat([{"role": "user", "content": "again"}])
        return first, second

    import asyncio
    first, second = asyncio.run(run())

    assert first.content == "from-plan"
    assert second.content == "from-plan"
    assert provider.active_channel == "plan"
    assert provider._paid_calls["n"] == 1, "粘性切换后不得再碰付费通道"
    assert any(e.get("code") == "provider_channel_switched" for e in events)
    status = provider.channel_status()
    assert status["active"] == "plan" and status["plan_available"] is True
    assert status["usage"]["plan"]["requests"] == 2
    assert status["usage"]["plan"]["total_tokens"] == 30
    assert status["usage"]["paid"]["requests"] == 0


def test_plain_rate_limit_429_does_not_switch() -> None:
    """限流 429 是「慢下来」不是「没钱了」——通道不得切换。"""
    provider = _provider(
        lambda n: (_ for _ in ()).throw(_rate_limit_429()),
        lambda n: _ok_payload("from-plan"),
    )

    async def run():
        try:
            await provider.chat([{"role": "user", "content": "hi"}])
        except RateLimitError:
            return "raised"

    import asyncio
    assert asyncio.run(run()) == "raised"
    assert provider.active_channel == "paid"
    assert provider.channel_status()["usage"]["plan"]["requests"] == 0


def test_credit_limit_429_switches_to_plan_channel() -> None:
    """带 credit 标识的 429 是「额度池空了」——必须切换。"""
    provider = _provider(
        lambda n: (_ for _ in ()).throw(_rate_limit_429(
            {"error": {"code": "insufficient_credit", "message": "Credit 已用尽"}}
        )),
        lambda n: _ok_payload("from-plan"),
    )

    async def run():
        return await provider.chat([{"role": "user", "content": "hi"}])

    import asyncio
    assert asyncio.run(run()).content == "from-plan"
    assert provider.active_channel == "plan"


def test_402_propagates_when_no_plan_channel_is_configured() -> None:
    """没配套餐通道时保持原语义：402 原样抛给上层（有界失败，不是挂死）。"""
    provider = _provider(lambda n: (_ for _ in ()).throw(_quota_402()))

    async def run():
        try:
            await provider.chat([{"role": "user", "content": "hi"}])
        except APIStatusError:
            return "raised"

    import asyncio
    assert asyncio.run(run()) == "raised"
    assert provider.active_channel == "paid"


def test_plan_channel_that_also_fails_propagates_instead_of_looping() -> None:
    """套餐通道也没钱时如实失败：只切换一次，不做无限乒乓。"""
    provider = _provider(
        lambda n: (_ for _ in ()).throw(_quota_402()),
        lambda n: (_ for _ in ()).throw(_quota_402()),
    )

    async def run():
        try:
            await provider.chat([{"role": "user", "content": "hi"}])
        except APIStatusError:
            return "raised"

    import asyncio
    assert asyncio.run(run()) == "raised"
    assert provider.active_channel == "plan"


def test_quota_detector_distinguishes_slow_down_from_empty_pool() -> None:
    assert _is_quota_exhausted(_quota_402()) is True
    assert _is_quota_exhausted(_rate_limit_429({"error": {"code": "insufficient_credit"}})) is True
    assert _is_quota_exhausted(_rate_limit_429({"error": {"code": "project_credit_limit_exceeded"}})) is True
    assert _is_quota_exhausted(_rate_limit_429()) is False
    assert _is_quota_exhausted(RuntimeError("unrelated")) is False
