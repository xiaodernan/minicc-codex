"""M8-T1119: the live workspace brief must never lie, never leak, never 500.

The model writes the brief from the measured fact pack only; errors surface as
an honest live=False; the memo holds repeated unlocks to one call.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import minicc.oracle_brief as ob
from minicc.config import load_config


def _fake_openai_response(zh: str = "中文简报", en: str = "english brief",
                          prompt_tokens: int = 900, completion_tokens: int = 120,
                          cached_tokens: int | None = 4224):
    class _Msg:
        content = json.dumps({"zh": zh, "en": en}, ensure_ascii=False)

    class _Usage:
        pass

    class _Choice:
        pass

    class _Resp:
        pass

    class _Details:
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
    if cached_tokens is None:
        resp.usage = usage
    else:
        details = _Details()
        details.cached_tokens = cached_tokens
        usage.prompt_tokens_details = details
        resp.usage = usage
    return resp


@pytest.fixture(autouse=True)
def _clear_cache():
    ob.default_cache.set(ob._CACHE_KEY, None, ttl=0)
    yield
    ob.default_cache.set(ob._CACHE_KEY, None, ttl=0)


def test_prompt_carries_the_measured_facts(monkeypatch, tmp_path) -> None:
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
    out = ob.build_workspace_brief(config=_config(), workspace=tmp_path)
    assert out["live"] is True
    prompt = captured["messages"][0]["content"]
    assert "total_commits" in prompt
    assert "/api/digest" not in prompt  # deps are the facts, not our API names
    assert "atlas_coordinates" not in prompt  # repo-owned constants are not invented facts
    assert '"tasks_completed"' in prompt or '"tasks_total"' in prompt


def test_live_brief_returns_both_languages_and_usage(monkeypatch, tmp_path) -> None:
    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return _fake_openai_response("提交 1,800 次。", "1,800 commits.")

    monkeypatch.setattr("openai.OpenAI", _Client)
    out = ob.build_workspace_brief(config=_config(), workspace=tmp_path)
    assert out["zh"] == "提交 1,800 次。"
    assert out["en"] == "1,800 commits."
    assert out["model"] == "test-model"
    assert out["usage"]["prompt_tokens"] == 900
    assert out["usage"]["completion_tokens"] == 120
    assert out["usage"]["cached_tokens"] == 4224  # gateway reported it; we surface it


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
    out = ob.build_workspace_brief(config=_config(), workspace=tmp_path)
    assert "cached_tokens" not in out["usage"]


def test_broken_model_returns_live_false_not_exception(monkeypatch, tmp_path) -> None:
    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("connection refused")

    monkeypatch.setattr("openai.OpenAI", _Client)
    out = ob.build_workspace_brief(config=_config(), workspace=tmp_path)
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
    first = ob.build_workspace_brief(config=_config(), workspace=tmp_path)
    second = ob.build_workspace_brief(config=_config(), workspace=tmp_path)
    assert calls["n"] == 1
    assert first["zh"] == second["zh"]
    # fresh=True bypasses the memo and hits the model again
    third = ob.build_workspace_brief(config=_config(), workspace=tmp_path, force_refresh=True)
    assert calls["n"] == 2
    assert third["live"] is True


def test_non_json_model_text_still_ships_as_a_brief(monkeypatch, tmp_path) -> None:
    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    class _Msg:
                        content = "工作区很大，提交很多。\nIt is big."

                    class _Choice:
                        message = _Msg()

                    class _Resp:
                        choices = [_Choice()]

                    return _Resp()

    monkeypatch.setattr("openai.OpenAI", _Client)
    out = ob.build_workspace_brief(config=_config(), workspace=tmp_path)
    assert out["live"] is True
    assert "工作区很大" in out["zh"]


def _config(**overrides):
    base = dict(model="test-model", base_url="https://example.invalid/v1",
                api_key="test-key", prompt_cache_key="", timeout=60)
    base.update(overrides)
    return SimpleNamespace(**base)
