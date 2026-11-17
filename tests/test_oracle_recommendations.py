# -*- coding: utf-8 -*-
"""M8-T1196 — the recommendations oracle: model reads the same snapshot, answers with items.

Truth invariants: prompt carries the measured snapshot only; zero-signal (no
tasks, no cache reading, no events across the week) costs zero tokens; a model
failure is live:false, never raises; second call rides the memo.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import minicc.oracle_recommendations as orc
from minicc.oracle_common import default_cache


def _fake_openai_response(zh=None, en=None, cached_tokens=4224, prompt_tokens=1300,
                          completion_tokens=220):
    zh = zh or ["先修 audit_export 的 IO 带宽（c=32 时 10,008ms）", "把本地配额包进 retry budget", "把 ingested 的统计接进 starred 查询"]
    en = en or ["Fix audit_export's IO bandwidth (10,008ms at c=32)", "Wrap the local quota in a retry budget", "Wire ingestion into the starred query path"]

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
    default_cache.set(orc._CACHE_KEY, None, ttl=0)
    yield
    default_cache.set(orc._CACHE_KEY, None, ttl=0)


def _config(**overrides):
    base = dict(model="test-model", base_url="https://example.invalid/v1",
                api_key="test-key", prompt_cache_key="", timeout=60)
    base.update(overrides)
    return SimpleNamespace(**base)


def _seed_signal(monkeypatch, tmp_path, totals=None, trend=None, tool_usage=None, interrupt_causes=None):
    """Install canned (non-zero-signal) snapshot pieces; the model call is the only variable."""
    totals = totals or {"tasks": 4, "completed": 4, "interrupted": 0,
                        "cache_hit_rate": None, "audit_lines": 1617, "sessions": 165}
    trend = trend or [{"day": f"2026-11-{d:02d}", "events": 200 if d == 12 else d}
                      for d in range(10, 18)]
    tool_usage = tool_usage if tool_usage is not None else [{"name": "tree", "count": 4, "pct": 100.0}]
    summary = {
        "totals": totals,
        "interrupt_causes": interrupt_causes,
        "completion_streak": {"current": 2, "best": 2, "days": 2,
                              "last_completed": "2026-11-17"},
        "tool_usage": tool_usage,
        "trend_7d": trend,
        "recommendations": [],
    }
    stats = {"llm_cache": {"hit_rate": None}}
    monkeypatch.setattr("minicc.oracle_recommendations.build_summary", lambda ws: summary)
    monkeypatch.setattr("minicc.oracle_recommendations.gather", lambda ws: stats)
    return summary, stats


def test_prompt_carries_the_measured_evidence(monkeypatch, tmp_path) -> None:
    _seed_signal(monkeypatch, tmp_path)

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
    out = orc.build_workspace_recommendations(config=_config(), workspace=tmp_path)
    assert out["live"] is True
    prompt = captured["messages"][0]["content"]
    for marker in ("trend_7d", "llm_cache_rate", "tool_usage", "interrupt_causes", "audit_lines"):
        assert marker in prompt


def test_zero_signal_workspace_costs_zero_tokens(monkeypatch, tmp_path) -> None:
    called = []

    class _Client:
        def __init__(self, *a, **k):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    called.append(True)
                    raise AssertionError("model must not be called in zero-signal")

    monkeypatch.setattr("openai.OpenAI", _Client)

    summary = {
        "totals": {"tasks": 0, "completed": 0, "interrupted": 0,
                   "cache_hit_rate": None, "audit_lines": None, "sessions": 0},
        "interrupt_causes": None,
        "completion_streak": None,
        "tool_usage": [],
        "trend_7d": [{"day": f"2026-11-{d:02d}", "events": 0} for d in range(1, 8)],
        "recommendations": [],
    }
    stats = {"llm_cache": None}
    monkeypatch.setattr("minicc.oracle_recommendations.build_summary", lambda ws: summary)
    monkeypatch.setattr("minicc.oracle_recommendations.gather", lambda ws: stats)

    out = orc.build_workspace_recommendations(config=_config(), workspace=tmp_path,
                                              force_refresh=True)
    assert out["verdict"] == "no-signal"
    assert called == []
    assert out["zh"] and out["en"]


def test_model_failure_is_honest_not_raised(monkeypatch, tmp_path) -> None:
    _seed_signal(monkeypatch, tmp_path)

    class _Client:
        def __init__(self, *a, **k):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("provider exploded")

    monkeypatch.setattr("openai.OpenAI", _Client)
    out = orc.build_workspace_recommendations(config=_config(), workspace=tmp_path,
                                              force_refresh=True)
    assert out["live"] is False
    assert "RuntimeError" in out["error"]


def test_second_call_rides_the_memo(monkeypatch, tmp_path) -> None:
    _seed_signal(monkeypatch, tmp_path)
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
    first = orc.build_workspace_recommendations(config=_config(), workspace=tmp_path, force_refresh=True)
    second = orc.build_workspace_recommendations(config=_config(), workspace=tmp_path)
    assert calls["n"] == 1
    assert first["generated_at"] == second["generated_at"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-W", "error"]))
