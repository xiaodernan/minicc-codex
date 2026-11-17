"""M8-T1122: live 'first three moves' — the model orders the priorities.

Truth invariants: prompt carries the measured snapshot only; output parsed into
3 items per language; usage never fabricated; outage -> live:false, never raises.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import minicc.oracle_plan as op
from minicc.oracle_common import default_cache


def _fake_openai_response(zh=None, en=None, cached_tokens=4224,
                          prompt_tokens=1200, completion_tokens=150):
    zh = zh or ["先盯着这 3 次中断的共同栈", "跑一遍 pytest -k restart 定位", "把 warm keeper 间隔压到 90s"]
    en = en or ["Triage the 3 restart-linked interruptions", "Run pytest -k restart to pin it", "Tighten the warm keeper to 90s"]
    class _Msg:
        content = json.dumps({"zh": zh, "en": en}, ensure_ascii=False)

    class _Usage:
        pass

    class _Choice:
        pass

    class _Resp:
        pass

    msg = _Msg()
    choice = _Choice()
    choice.message = msg
    resp = _Resp()
    resp.choices = [choice]
    usage = _Usage()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    usage.total_tokens = prompt_tokens + completion_tokens
    if cached_tokens is not None:
        class _Details:
            pass
        d = _Details()
        d.cached_tokens = cached_tokens
        usage.prompt_tokens_details = d
    resp.usage = usage
    return resp


@pytest.fixture(autouse=True)
def _clear_cache():
    default_cache.set(op._CACHE_KEY, None, ttl=0)
    yield
    default_cache.set(op._CACHE_KEY, None, ttl=0)


def _config(**overrides):
    base = dict(model="test-model", base_url="https://example.invalid/v1",
                api_key="test-key", prompt_cache_key="", timeout=60)
    base.update(overrides)
    return SimpleNamespace(**base)


def test_prompt_carries_the_measured_evidence(monkeypatch, tmp_path) -> None:
    captured = {}

    class _Client:
        def __init__(self, *a, **k):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    captured.update(kwargs)
                    return _fake_openai_response()

    monkeypatch.setattr("openai.OpenAI", _Client)
    out = op.build_workspace_plan(config=_config(), workspace=tmp_path)
    assert out["live"] is True
    prompt = captured["messages"][0]["content"]
    assert "interrupt_causes" in prompt
    assert "tool_usage" in prompt
    assert "trend_7d" in prompt
    assert "recommendations" in prompt


def test_live_plan_returns_three_bilingual_items_and_usage(monkeypatch, tmp_path) -> None:
    class _Client:
        def __init__(self, *a, **k):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return _fake_openai_response()

    monkeypatch.setattr("openai.OpenAI", _Client)
    out = op.build_workspace_plan(config=_config(), workspace=tmp_path)
    assert len(out["zh"]) == 3
    assert len(out["en"]) == 3
    assert out["usage"]["cached_tokens"] == 4224
    assert out["model"] == "test-model"


def test_cached_tokens_absent_is_reported_not_fabricated(monkeypatch, tmp_path) -> None:
    class _Client:
        def __init__(self, *a, **k):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return _fake_openai_response(cached_tokens=None)

    monkeypatch.setattr("openai.OpenAI", _Client)
    out = op.build_workspace_plan(config=_config(), workspace=tmp_path)
    assert "cached_tokens" not in out["usage"]


def test_broken_wire_returns_live_false_not_exception(monkeypatch, tmp_path) -> None:
    class _Client:
        def __init__(self, *a, **k):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("connection refused")

    monkeypatch.setattr("openai.OpenAI", _Client)
    out = op.build_workspace_plan(config=_config(), workspace=tmp_path)
    assert out["live"] is False
    assert "connection refused" in out["error"]
    assert out["zh"] == []


def test_memo_serves_second_call_without_a_second_model_round_trip(monkeypatch, tmp_path) -> None:
    calls = {"n": 0}

    class _Client:
        def __init__(self, *a, **k):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    calls["n"] += 1
                    return _fake_openai_response()

    monkeypatch.setattr("openai.OpenAI", _Client)
    first = op.build_workspace_plan(config=_config(), workspace=tmp_path)
    second = op.build_workspace_plan(config=_config(), workspace=tmp_path)
    assert calls["n"] == 1
    assert first["zh"] == second["zh"]
    third = op.build_workspace_plan(config=_config(), workspace=tmp_path, force_refresh=True)
    assert calls["n"] == 2
    assert third["live"] is True


def test_malformed_json_still_ships_lines(monkeypatch, tmp_path) -> None:
    class _Client:
        def __init__(self, *a, **k):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    class _Msg:
                        content = "做了甲\n做了乙"

                    class _Choice:
                        message = _Msg()

                    class _Resp:
                        choices = [_Choice()]

                    return _Resp()

    monkeypatch.setattr("openai.OpenAI", _Client)
    out = op.build_workspace_plan(config=_config(), workspace=tmp_path)
    assert out["live"] is True
    assert any("甲" in line for line in out["zh"])
