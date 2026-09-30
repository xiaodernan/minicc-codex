"""M8-T60: Anthropic 路径的双通道——与 M8-T55 同判据，另一个协议面。

Step Plan 的 Anthropic 兼容端点（https://api.stepfun.com/step_plan）与付费
端点用同一把 key（x-api-key 不变），只有 base URL 不同。付费池耗尽时切换，
切换粘性；credit 型 429 在没有套餐通道时立刻死（不烧无意义的重试），
普通限流 429 保持既有重试语义。
"""

from __future__ import annotations

import httpx
import pytest

from minicc.llm.anthropic_provider import AnthropicProvider, AnthropicProviderError

PAID_URL = "https://api.stepfun.com/v1"
PLAN_URL = "https://api.stepfun.com/step_plan/v1"

_OK_PAYLOAD = {
    "model": "claude-test",
    "stop_reason": "end_turn",
    "content": [{"type": "text", "text": "from-plan"}],
    "usage": {"input_tokens": 10, "output_tokens": 5},
}


def _provider(requests: list[httpx.Request], *, plan: bool = True, responses: list[httpx.Response] | None = None, max_retries: int = 0):
    """responses: 依次弹出的应答；弹完后默认 200 _OK_PAYLOAD。"""
    queue = list(responses or [])

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if queue:
            return queue.pop(0)
        return httpx.Response(200, json=_OK_PAYLOAD)

    return AnthropicProvider(
        api_key="test-key",
        model="claude-test",
        base_url=PAID_URL,
        plan_base_url=PLAN_URL if plan else "",
        max_retries=max_retries,
        transport=httpx.MockTransport(handler),
    )


def _calls_to_urls(requests: list[httpx.Request]) -> list[str]:
    return [str(r.url) for r in requests]


@pytest.mark.asyncio()
async def test_402_switches_to_plan_and_is_sticky() -> None:
    requests: list[httpx.Request] = []
    provider = _provider(
        requests,
        responses=[
            httpx.Response(402, json={"error": {"message": "余额不足"}}),
        ],
    )
    first = await provider.chat([{"role": "user", "content": "hi"}])
    second = await provider.chat([{"role": "user", "content": "again"}])

    assert first.content == "from-plan"
    assert second.content == "from-plan"
    assert provider.active_channel == "plan"
    urls = _calls_to_urls(requests)
    assert "step_plan" not in urls[0], "第一个请求打在付费端点吃 402"
    assert all("step_plan" in u for u in urls[1:]), "切换后全部走套餐端点（粘性）"
    status = provider.channel_status()
    assert status["active"] == "plan" and status["plan_available"] is True
    assert status["usage"]["plan"]["requests"] == 2
    # 单次 usage total = input 10 + output 5；两次调用共 30。
    assert status["usage"]["plan"]["total_tokens"] == 30


@pytest.mark.asyncio()
async def test_credit_limit_429_switches() -> None:
    requests: list[httpx.Request] = []
    provider = _provider(
        requests,
        responses=[
            httpx.Response(429, json={"error": {"code": "insufficient_credit", "message": "Credit 已用尽"}}),
        ],
    )
    response = await provider.chat([{"role": "user", "content": "hi"}])
    assert response.content == "from-plan"
    assert provider.active_channel == "plan"


@pytest.mark.asyncio()
async def test_402_without_plan_raises_immediately() -> None:
    requests: list[httpx.Request] = []
    provider = _provider(
        requests,
        plan=False,
        responses=[httpx.Response(402, json={"error": {"message": "余额不足"}})],
    )
    with pytest.raises(AnthropicProviderError, match="402"):
        await provider.chat([{"role": "user", "content": "hi"}])
    assert len(requests) == 1, "没配套餐通道时不重试，402 原样失败"


@pytest.mark.asyncio()
async def test_credit_429_without_plan_dies_without_burning_retries() -> None:
    requests: list[httpx.Request] = []
    provider = _provider(
        requests,
        plan=False,
        responses=[
            httpx.Response(429, json={"error": {"code": "insufficient_credit", "message": "Credit 已用尽"}}),
            httpx.Response(200, json=_OK_PAYLOAD),
            httpx.Response(200, json=_OK_PAYLOAD),
            httpx.Response(200, json=_OK_PAYLOAD),
        ],
    )
    with pytest.raises(AnthropicProviderError, match="insufficient_credit|429"):
        await provider.chat([{"role": "user", "content": "hi"}])
    assert len(requests) == 1, "credit 型 429 是「池子空了」，重试无意义——必须一次就死"


@pytest.mark.asyncio()
async def test_plain_rate_limit_429_keeps_retry_semantics() -> None:
    """普通限流 429（无 credit 码）不切换、按原语义重试。"""
    requests: list[httpx.Request] = []
    provider = _provider(
        requests,
        responses=[
            httpx.Response(429, json={"error": {"message": "request limited RPM reached"}}),
        ],
        max_retries=1,
    )
    response = await provider.chat([{"role": "user", "content": "hi"}])
    assert response.content == "from-plan"
    assert provider.active_channel == "paid"
    assert all("step_plan" not in u for u in _calls_to_urls(requests))
