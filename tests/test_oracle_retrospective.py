"""M8-T1125: the model-duty retrospective — reads the audit journal honestly.

Truth invariants: prompt carries cited snapshot; outage -> live:false; memo.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import minicc.oracle_retrospective as ot
from minicc.oracle_common import default_cache


def _fake_openai_response(zh="最近完成任务可信。", en="The recent completion claim is plausible.",
                          cached_tokens=None, prompt_tokens=300, completion_tokens=80):
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
    default_cache.set(ot._CACHE_KEY, None, ttl=0)
    yield
    default_cache.set(ot._CACHE_KEY, None, ttl=0)


def _config(**overrides):
    base = dict(model="test-model", base_url="https://example.invalid/v1",
                api_key="test-key", prompt_cache_key="", timeout=30)
    base.update(overrides)
    return SimpleNamespace(**base)


def test_prompt_carries_the_record_no_extra_facts(monkeypatch, tmp_path) -> None:
    captured: dict = {}

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
    out = ot.build_workspace_retrospective(config=_config(), workspace=tmp_path)
    assert out["live"] is True
    prompt = captured["messages"][0]["content"]
    for forbidden in ["git diff", "git show", "SELECT", "home_dir"]:
        assert forbidden not in prompt
    payload = prompt.split("快照：", 1)[-1]
    assert '"last_task"' in payload
    assert '"other_recent"' in payload
    assert '"cache_hit_rate"' in payload


def test_live_retrospective_returns_en_zh_and_model(monkeypatch, tmp_path) -> None:
    class _Client:
        def __init__(self, *a, **k):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return _fake_openai_response()

    monkeypatch.setattr("openai.OpenAI", _Client)
    out = ot.build_workspace_retrospective(config=_config(), workspace=tmp_path)
    assert out["zh"].startswith("最近")
    assert out["en"].startswith("The recent")
    assert out["model"] == "test-model"


def test_broken_wire_returns_live_false(monkeypatch, tmp_path) -> None:
    class _Broken:
        def __init__(self, *a, **k):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("nope")

    monkeypatch.setattr("openai.OpenAI", _Broken)
    out = ot.build_workspace_retrospective(config=_config(), workspace=tmp_path)
    assert out["live"] is False
    assert "nope" in out["error"]
    assert out["zh"] == ""


def test_memo_call_guard(monkeypatch, tmp_path) -> None:
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
    first = ot.build_workspace_retrospective(config=_config(), workspace=tmp_path)
    second = ot.build_workspace_retrospective(config=_config(), workspace=tmp_path)
    assert calls["n"] == 1
    assert first["zh"] == second["zh"]
    third = ot.build_workspace_retrospective(config=_config(), workspace=tmp_path, force_refresh=True)
    assert calls["n"] == 2
