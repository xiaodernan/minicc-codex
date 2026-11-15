"""M8-T1003: the prefix cache keeper — honest, bounded, never raises.

The keeper fires one tiny gateway decision against the same wire the agent
speaks, carrying the same derived ``prompt_cache_key``; it exists so the
shared system prompt survives idle gaps on the upstream gateway. These
tests stub ``_call_gateway`` completely — no gateway is contacted.
"""

from __future__ import annotations

import asyncio

import pytest

import minicc.cache_keeper as ck


@pytest.fixture(autouse=True)
def _reset_state():
    with ck._STATE_GUARD:
        for key, value in list(ck._STATE.items()):
            ck._STATE[key] = None if key in {
                "enabled", "interval_seconds", "started_at", "last_warm_at",
                "last_ok", "last_error", "last_prompt_tokens", "last_cached_tokens",
                "last_elapsed_ms",
            } else 0
    yield


class _Usage:
    def __init__(self, prompt: int, cached: int):
        self.input_tokens = prompt
        self.input_tokens_details = _Details(cached)
        self.output_tokens = 1
        self.total_tokens = prompt + 1


class _Details:
    def __init__(self, cached: int):
        self.cached_tokens = cached


class _Resp:
    def __init__(self, prompt: int, cached: int):
        self.usage = _Usage(prompt, cached)


def test_key_derivation_is_stable_and_model_sensitive() -> None:
    a = ck._derive_cache_key("https://wkapi.pro/v1", "gpt-6-sol")
    b = ck._derive_cache_key("https://wkapi.pro/v1", "gpt-6-sol")
    c = ck._derive_cache_key("https://wkapi.pro/v1", "gpt-6.5-sol")
    assert a == b
    assert a != c
    assert a.startswith("minicc-") and len(a) == len("minicc-") + 16


def test_enabled_defaults_on_and_honors_the_off_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MINICC_CACHE_KEEPER", raising=False)
    assert ck.enabled() is True
    monkeypatch.setenv("MINICC_CACHE_KEEPER", "0")
    assert ck.enabled() is False
    monkeypatch.setenv("MINICC_CACHE_KEEPER", "off")
    assert ck.enabled() is False


def test_warm_once_records_success_state(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_call(**kwargs):
        assert kwargs["cache_key"].startswith("minicc-")
        return {"prompt_tokens": 7537, "cached_tokens": 7400}

    monkeypatch.setattr(ck, "_call_gateway", fake_call)
    keeper = ck.CacheKeeper(
        base_url="https://wkapi.pro/v1",
        model="gpt-6-sol",
        api_key="sk-test-not-a-real-key",
        system_prompt="你是 minicc",
        interval=300,
    )
    keeper._warm_once()
    state = ck.keeper_status()
    assert state["warms"] == 1
    assert state["failures"] == 0
    assert state["last_ok"] is True
    assert state["last_cached_tokens"] == 7400
    assert state["last_prompt_tokens"] == 7537
    assert state["last_elapsed_ms"] is not None


def test_warm_once_records_failure_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(**kwargs):
        raise RuntimeError("gateway declined")

    monkeypatch.setattr(ck, "_call_gateway", boom)
    keeper = ck.CacheKeeper(
        base_url="https://wkapi.pro/v1",
        model="gpt-6-sol",
        api_key="sk-test-not-a-real-key",
        system_prompt="你是 minicc",
        interval=300,
    )
    keeper._warm_once()
    state = ck.keeper_status()
    assert state["warms"] == 0
    assert state["failures"] == 1
    assert state["last_ok"] is False
    assert state["last_error"] == "RuntimeError"


def test_keeper_refuses_to_start_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MINICC_CACHE_KEEPER", raising=False)
    keeper = ck.CacheKeeper(base_url="", model="", api_key="", system_prompt="")
    keeper.start()
    state = ck.keeper_status()
    assert state["enabled"] is False
    assert keeper._thread is None
