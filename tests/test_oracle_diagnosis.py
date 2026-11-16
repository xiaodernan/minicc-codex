"""M8-T1120: the model-duty diagnosis must be honest, grounded, and free.

Same contract as the workspace brief: prompt carries only the measured
interruption/streak/tool evidence, never their conclusions; the wire error
degrades to live:false; the memo holds repeated unlocks to one model call.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import minicc.oracle_diagnosis as od
from minicc.oracle_common import default_cache


def _fake_openai_response(zh: str = "中文诊断", en: str = "english diagnosis",
                          prompt_tokens: int = 1100, completion_tokens: int = 160,
                          cached_tokens: int | None = 4224):
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

        details = _Details()
        details.cached_tokens = cached_tokens
        usage.prompt_tokens_details = details
    resp.usage = usage
    return resp


@pytest.fixture(autouse=True)
def _clear_cache():
    default_cache.set(od._CACHE_KEY, None, ttl=0)
    yield
    default_cache.set(od._CACHE_KEY, None, ttl=0)


def _config(**overrides):
    base = dict(model="test-model", base_url="https://example.invalid/v1",
                api_key="test-key", prompt_cache_key="", timeout=60)
    base.update(overrides)
    return SimpleNamespace(**base)


def test_prompt_carries_the_interruption_evidence(monkeypatch, tmp_path) -> None:
    captured = {}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    captured.update(kwargs)
                    return _fake_openai_response()

    monkeypatch.setattr("openai.OpenAI", _Client)
    out = od.build_workspace_diagnosis(config=_config(), workspace=tmp_path)
    assert out["live"] is True
    prompt = captured["messages"][0]["content"]
    assert "interrupt_causes" in prompt
    assert "completion_streak" in prompt
    assert "trend_7d" in prompt
    assert "recommendations" in prompt


def test_live_diagnosis_returns_both_languages_and_usage(monkeypatch, tmp_path) -> None:
    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return _fake_openai_response("重启导致 3 次中断。", "Three interruptions came from restarts.")

    monkeypatch.setattr("openai.OpenAI", _Client)
    out = od.build_workspace_diagnosis(config=_config(), workspace=tmp_path)
    assert out["zh"] == "重启导致 3 次中断。"
    assert out["en"] == "Three interruptions came from restarts."
    assert out["model"] == "test-model"
    assert out["usage"]["prompt_tokens"] == 1100
    assert out["usage"]["cached_tokens"] == 4224


def test_cached_tokens_absent_is_reported_not_fabricated(monkeypatch, tmp_path) -> None:
    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return _fake_openai_response(cached_tokens=None)

    monkeypatch.setattr("openai.OpenAI", _Client)
    out = od.build_workspace_diagnosis(config=_config(), workspace=tmp_path)
    assert "cached_tokens" not in out["usage"]


def test_broken_wire_returns_live_false_not_exception(monkeypatch, tmp_path) -> None:
    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("connection refused")

    monkeypatch.setattr("openai.OpenAI", _Client)
    out = od.build_workspace_diagnosis(config=_config(), workspace=tmp_path)
    assert out["live"] is False
    assert "connection refused" in out["error"]
    assert out["zh"] == ""


def test_memo_serves_second_call_without_a_second_model_round_trip(monkeypatch, tmp_path) -> None:
    calls = {"n": 0}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    calls["n"] += 1
                    return _fake_openai_response()

    monkeypatch.setattr("openai.OpenAI", _Client)
    first = od.build_workspace_diagnosis(config=_config(), workspace=tmp_path)
    second = od.build_workspace_diagnosis(config=_config(), workspace=tmp_path)
    assert calls["n"] == 1
    assert first["zh"] == second["zh"]
    third = od.build_workspace_diagnosis(config=_config(), workspace=tmp_path, force_refresh=True)
    assert calls["n"] == 2
    assert third["live"] is True


def test_non_json_model_text_still_ships_as_a_diagnosis(monkeypatch, tmp_path) -> None:
    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    class _Msg:
                        content = "重启导致中断。\nInterruptions tie to restarts."

                    class _Choice:
                        message = _Msg()

                    class _Resp:
                        choices = [_Choice()]

                    return _Resp()

    monkeypatch.setattr("openai.OpenAI", _Client)
    out = od.build_workspace_diagnosis(config=_config(), workspace=tmp_path)
    assert out["live"] is True
    assert "重启导致中断" in out["zh"]
