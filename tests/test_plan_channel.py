"""双通道 provider 测试（M8-T55）：主通道额度用尽时切换到 Step Plan 套餐通道。

Step Plan（订阅 Credit 月池）与付费 API 用同一类 API Key，但 base URL 不同、
额度独立。付费通道耗尽时任务会以 402 / Credit 型 429 死掉——本文件钉住
「死掉就切换、切换是粘性的、限流不误判切换」这三条契约。

后半段（M8-T59）钉的是另一件事：切换要作用在**每一条** SDK 请求路径上。
provider 有三处 `create()`（responses 非流、responses 流、chat completions），
前半段的七条测试全部走 chat_completions、且全部直接注入 `_plan_client`，
所以另外两条路径与「套餐客户端到底是用什么凭据建出来的」此前只有 grep 保证。
"""

from __future__ import annotations

import ast
import asyncio
import functools
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import httpx
import pytest
from openai import APIStatusError, RateLimitError

import minicc.llm.openai_provider as provider_module
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


# -- 每一条 SDK 请求路径都要走通道感知客户端（M8-T59）--------------------------

PROVIDER_SOURCE = Path(__file__).resolve().parents[1] / "minicc" / "llm" / "openai_provider.py"
REPO_ROOT = PROVIDER_SOURCE.parents[2]

#: The wire surfaces the provider sends model requests through, innermost last.
SDK_REQUEST_CHAINS = frozenset({("responses", "create"), ("chat", "completions", "create")})

#: Measured 2026-09-26: three request sites in the provider.
_MIN_REQUEST_SITES = 3


def _sdk_request_sites(source: str) -> list[str]:
    """One label per SDK request call, naming the expression the client comes from.

    The match is on the *tail* of the attribute chain, because the bypass this
    gate exists to catch is exactly the shape with more links in front of it:
    `self.client.responses.create(...)` reads back as `responses.create on self.client`,
    `self._active_client().responses.create(...)` as `responses.create on self._active_client()`.
    """
    sites: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        chain: list[str] = []
        cursor: Any = node.func
        while isinstance(cursor, ast.Attribute):
            chain.append(cursor.attr)
            cursor = cursor.value
        links = tuple(reversed(chain))
        matched = next((chain_ for chain_ in SDK_REQUEST_CHAINS if links[-len(chain_):] == chain_), None)
        if matched is None:
            continue
        func_src = ast.get_source_segment(source, node.func) or ""
        prefix = func_src[: -len(".".join(matched))].rstrip(".")
        sites.append(f"line {node.lineno}: {'.'.join(matched)} on {prefix}")
    return sorted(sites)


def _responses_ok(mark: str) -> SimpleNamespace:
    """The shape `_responses_to_response` reads: output items plus token usage."""
    return SimpleNamespace(
        id="resp-plan",
        status="completed",
        model="test-model",
        output=[
            SimpleNamespace(
                type="message",
                content=[SimpleNamespace(type="output_text", text=mark)],
            )
        ],
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=5,
            input_tokens_details=SimpleNamespace(cached_tokens=0),
        ),
    )


class _FakeStream:
    def __init__(self, events: list[Any]) -> None:
        self._events = events

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for event in self._events:
            yield event


def _responses_stream(mark: str) -> _FakeStream:
    return _FakeStream([
        SimpleNamespace(type="response.output_text.delta", delta=mark),
        SimpleNamespace(
            type="response.completed",
            response=_responses_ok(mark),
        ),
    ])


class _BuiltClient:
    """Stand-in for `openai.AsyncOpenAI(...)`, with both request surfaces real.

    Records which surface each call arrived on, because "a create() happened"
    does not yet prove which of the provider's three request sites was run.
    """

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.calls: list[dict[str, Any]] = []
        self.behaviour: Callable[[_BuiltClient, dict[str, Any]], Any] | None = None
        self.responses = SimpleNamespace(create=functools.partial(self._create, "responses"))
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=functools.partial(self._create, "chat"))
        )

    async def _create(self, surface: str, **kwargs: Any) -> Any:
        entry = {"surface": surface, **kwargs}
        self.calls.append(entry)
        assert self.behaviour is not None, "fake SDK client built without a behaviour"
        return self.behaviour(self, entry)

    @property
    def api_key(self) -> str:
        return str(self.kwargs.get("api_key") or "")

    def surfaces(self) -> set[str]:
        return {str(call["surface"]) for call in self.calls}


def _patch_sdk(
    monkeypatch: pytest.MonkeyPatch,
    behaviours: dict[str, Callable[[_BuiltClient, dict[str, Any]], Any]],
) -> list[_BuiltClient]:
    """Replace the SDK entry point so every client the provider builds is recorded.

    `behaviours` is keyed by API key, so a test can say "the one holding the plan
    key answers this" without reaching into the provider's private attributes.
    """
    built: list[_BuiltClient] = []

    def factory(**kwargs: Any) -> _BuiltClient:
        client = _BuiltClient(**kwargs)
        client.behaviour = behaviours[kwargs["api_key"]]
        built.append(client)
        return client

    monkeypatch.setattr(provider_module, "AsyncOpenAI", factory)
    return built


def _dual_channel_provider(protocol: str) -> OpenAICompatibleProvider:
    """A provider with no injected client at all: it must build both of them."""
    return OpenAICompatibleProvider(
        "https://gateway.test/v1",
        "paid-key",
        "test-model",
        protocol=protocol,
        max_retries=0,
        plan_base_url="https://gateway.test/step_plan/v1",
        plan_api_key="plan-key",
    )


def _paid_dies_plan_answers(
    mark: str, payload: Callable[[str], Any]
) -> dict[str, Callable[[_BuiltClient, dict[str, Any]], Any]]:
    return {
        "paid-key": lambda client, _call: (_ for _ in ()).throw(_quota_402()),
        "plan-key": lambda client, _call: payload(mark),
    }


def test_every_sdk_request_site_goes_through_the_channel_aware_client() -> None:
    """A fourth `create()` that grabs a fixed client would silently ignore the flip."""
    sites = _sdk_request_sites(PROVIDER_SOURCE.read_text(encoding="utf-8"))
    assert len(sites) >= _MIN_REQUEST_SITES, f"the request sites vanished from view: {sites}"
    offenders = [site for site in sites if "_active_client()" not in site]
    assert offenders == [], f"SDK requests that ignore the active channel: {offenders}"


def test_the_site_scanner_reddens_a_fixed_client_and_ignores_unrelated_creates() -> None:
    for bypass in (
        "class P:\n    async def a(self):\n"
        "        return await self.client.responses.create(model='m')\n",
        "class P:\n    async def a(self):\n"
        "        return await self._client.chat.completions.create(model='m')\n",
        "class P:\n    async def a(self, client):\n"
        "        return await client.responses.create(model='m')\n",
    ):
        sites = _sdk_request_sites(bypass)
        assert len(sites) == 1, sites
        assert "_active_client()" not in sites[0], sites[0]

    pinned = _sdk_request_sites(
        "class P:\n    async def a(self):\n"
        "        return await self._active_client().chat.completions.create(model='m')\n"
    )
    assert len(pinned) == 1 and "_active_client()" in pinned[0], pinned

    unrelated = _sdk_request_sites(
        "def f(session, db):\n    session.create(user='x')\n    return db.close()\n"
    )
    assert unrelated == [], unrelated


def test_the_plan_client_is_built_by_the_provider_from_plan_credentials(monkeypatch) -> None:
    """The flip is only real if the client built for it carries the plan's URL and key.

    Every earlier test injected `_plan_client`, so the construction branch had no
    witness: a build that reused the paid key, or skipped `_sdk_base_url`, passed green.
    """
    built = _patch_sdk(monkeypatch, _paid_dies_plan_answers("from-lazy-plan", _ok_payload))
    provider = _dual_channel_provider("chat_completions")

    result = asyncio.run(provider.chat([{"role": "user", "content": "hi"}]))

    assert result.content == "from-lazy-plan"
    assert [client.api_key for client in built] == ["paid-key", "plan-key"], built
    plan = built[-1]
    assert plan.kwargs["base_url"] == "https://gateway.test/step_plan/v1", plan.kwargs
    assert plan.kwargs["max_retries"] == 0, "the SDK must not retry behind the channel flip"
    assert plan.surfaces() == {"chat"}
    assert provider.active_channel == "plan"


def test_quota_402_switches_the_non_stream_responses_channel(monkeypatch) -> None:
    built = _patch_sdk(monkeypatch, _paid_dies_plan_answers("from-plan-responses", _responses_ok))
    provider = _dual_channel_provider("responses")

    result = asyncio.run(provider.chat([{"role": "user", "content": "hi"}]))

    assert result.content == "from-plan-responses"
    assert built[0].surfaces() == {"responses"}, "the responses wire path was not exercised"
    assert built[-1].surfaces() == {"responses"}
    assert len(built[0].calls) == 1, "sticky flip must not touch the paid channel again"
    assert provider.channel_status()["usage"]["plan"]["requests"] == 1


def test_quota_402_switches_the_streaming_responses_channel(monkeypatch) -> None:
    """The stream site builds its own kwargs and its own client call, so it can drift alone."""
    built = _patch_sdk(monkeypatch, _paid_dies_plan_answers("来自套餐", _responses_stream))
    provider = _dual_channel_provider("responses")
    deltas: list[str] = []

    result = asyncio.run(
        provider.chat([{"role": "user", "content": "hi"}], on_delta=deltas.append)
    )

    assert deltas == ["来自套餐"], deltas
    assert result.content == "来自套餐"
    assert built[0].calls[-1].get("stream") is True, "paid was asked for a non-stream response"
    assert built[-1].calls[-1].get("stream") is True
    assert built[-1].surfaces() == {"responses"}
    assert provider.active_channel == "plan"


#: The two places that build a provider for a real session (measured 2026-09-26:
#: the CLI at minicc/main.py and the web/API factory at minicc/web.py).
PROVIDER_BUILD_SOURCES = ("minicc/main.py", "minicc/web.py")
_MIN_BUILD_SITES = 2


def _provider_build_sites(source: str) -> list[str]:
    """One label per `OpenAICompatibleProvider(...)` call, listing its keyword arguments.

    A build that omits `plan_base_url` leaves that session on a single channel
    forever: the 402 still arrives, and `_is_quota_exhausted` still fires, but
    `_has_plan_channel()` is False, so the task dies exactly as it did before
    the dual channel existed - with every test in this file still green.
    """
    sites: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        if name != "OpenAICompatibleProvider":
            continue
        keywords = sorted(str(kw.arg) for kw in node.keywords if kw.arg)
        sites.append(f"line {node.lineno}: {keywords}")
    return sorted(sites)


def test_every_provider_build_hands_over_both_plan_channel_knobs() -> None:
    sites: list[str] = []
    for relative in PROVIDER_BUILD_SOURCES:
        found = _provider_build_sites((REPO_ROOT / relative).read_text(encoding="utf-8"))
        assert found, f"{relative} no longer builds a provider; where did the session go?"
        sites.extend(f"{relative} {site}" for site in found)
    assert len(sites) >= _MIN_BUILD_SITES, sites
    offenders = [
        site for site in sites if "plan_api_key" not in site or "plan_base_url" not in site
    ]
    assert offenders == [], f"provider builds with no second channel: {offenders}"


def test_the_build_scanner_reddens_a_knob_less_build_and_ignores_other_calls() -> None:
    missing = _provider_build_sites(
        "p = OpenAICompatibleProvider(base_url='u', api_key='k', model='m', protocol='responses')\n"
    )
    assert len(missing) == 1, missing
    assert "plan_base_url" not in missing[0]

    wired = _provider_build_sites(
        "p = OpenAICompatibleProvider(\n"
        "    base_url='u', api_key='k', model='m',\n"
        "    plan_base_url='p', plan_api_key='pk',\n"
        ")\n"
    )
    assert len(wired) == 1 and "plan_base_url" in wired[0] and "plan_api_key" in wired[0], wired

    assert _provider_build_sites("x = AnthropicProvider(base_url='u', api_key='k')\n") == []
