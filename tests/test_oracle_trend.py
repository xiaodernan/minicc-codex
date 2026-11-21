# -*- coding: utf-8 -*-
"""M8-T1287 — the trend oracle: model reads the real 7-day series, writes a verdict.

Truth invariants: the prompt carries the measured trend + rule baseline only;
zero-signal (no tasks, no cache reading, no events) costs zero tokens; a model
failure or an unparsable answer is live:false, never raises; the second call
rides the memo; a direction outside the vocabulary fails closed to "unknown".
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import minicc.oracle_trend as orc
from minicc.oracle_common import default_cache


def _fake_response(payload=None, *, text=None, cached_tokens=4224, prompt_tokens=1300,
                   completion_tokens=220):
    raw = text if text is not None else json.dumps(
        payload or {
            "direction": "cooling",
            "zh": {"narrative": "峰值 11-12 达 200 次后回落，近两日仅 12 次。",
                   "moves": ["给 audit 导出加带宽上限（c=32 时 10,008ms）"]},
            "en": {"narrative": "Peak 200 on 11-12 then cooled; last two days averaged 12.",
                   "moves": ["Cap audit export bandwidth (10,008ms at c=32)"]},
        }, ensure_ascii=False)

    class _Msg:
        content = raw

    class _Choice:
        pass

    class _Resp:
        pass

    choice = _Choice()
    choice.message = _Msg()
    resp = _Resp()
    resp.choices = [choice]

    class _Usage:
        pass

    usage = _Usage()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    usage.total_tokens = prompt_tokens + completion_tokens

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


def _seed_signal(monkeypatch, *, forecast_direction="down", trend_events=None):
    trend_events = trend_events or [3, 200, 5, 4, 12, 11, 2]
    summary = {
        "totals": {"tasks": 4, "completed": 4, "interrupted": 0,
                   "cache_hit_rate": 0.9, "audit_lines": 1617, "sessions": 165},
        "trend_7d": [{"day": f"2026-11-{10 + i:02d}", "events": e}
                     for i, e in enumerate(trend_events)],
        "forecast": {"direction": forecast_direction, "slope_per_day": -12.5,
                     "peak_day": "2026-11-11", "peak_events": 200,
                     "last_2_avg": 11.5, "decline_from_peak": 0.94},
        "interrupt_causes": {"service restart": 2},
        "completion_streak": {"current": 2, "best": 2},
        "tool_usage": [{"name": "tree", "count": 4, "pct": 100.0}],
        "recommendations": [],
    }
    stats = {"llm_cache": {"hit_rate": 0.78}}
    monkeypatch.setattr("minicc.oracle_trend.build_summary", lambda ws: summary)
    monkeypatch.setattr("minicc.oracle_trend.gather", lambda ws: stats)
    return summary, stats


def test_prompt_carries_trend_and_rule_baseline(monkeypatch, tmp_path) -> None:
    _seed_signal(monkeypatch)
    captured = {}

    class _Client:
        def __init__(self, *a, **k):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    captured.update(kwargs)
                    return _fake_response()

    monkeypatch.setattr("openai.OpenAI", _Client)
    out = orc.build_trend_insight(config=_config(), workspace=tmp_path)
    assert out["live"] is True
    prompt = captured["messages"][0]["content"]
    for marker in ("trend_7d", "forecast", "interrupt_causes", "llm_cache_rate", "cooling"):
        assert marker in prompt
    # The measured series and the rule verdict are both in the prompt.
    assert "2026-11-11" in prompt


def test_verdict_grounded_and_baseline_recorded(monkeypatch, tmp_path) -> None:
    _seed_signal(monkeypatch, forecast_direction="down")

    class _Client:
        def __init__(self, *a, **k):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return _fake_response()

    monkeypatch.setattr("openai.OpenAI", _Client)
    out = orc.build_trend_insight(config=_config(), workspace=tmp_path)
    assert out["direction"] == "cooling"
    assert out["baseline_direction"] == "down"
    assert out["zh"]["narrative"] and out["en"]["narrative"]
    assert out["zh"]["moves"] and out["en"]["moves"]
    assert out["verdict"] == "model-trend"
    assert out["usage"]["cached_tokens"] == 4224


def test_unknown_direction_fails_closed(monkeypatch, tmp_path) -> None:
    _seed_signal(monkeypatch)

    class _Client:
        def __init__(self, *a, **k):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return _fake_response({"direction": "sideways",
                                           "zh": {"narrative": "读数在侧移", "moves": []},
                                           "en": {"narrative": "readings drift sideways", "moves": []}})

    monkeypatch.setattr("openai.OpenAI", _Client)
    out = orc.build_trend_insight(config=_config(), workspace=tmp_path)
    assert out["direction"] == "unknown"
    assert out["live"] is True


def test_unparsable_answer_is_honest_outage(monkeypatch, tmp_path) -> None:
    _seed_signal(monkeypatch)

    class _Client:
        def __init__(self, *a, **k):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return _fake_response(text="I refuse to answer in JSON.")

    monkeypatch.setattr("openai.OpenAI", _Client)
    out = orc.build_trend_insight(config=_config(), workspace=tmp_path)
    assert out["live"] is False
    assert out["verdict"] == "unparsable-model-answer"
    # The panel can read the same keys whether live or dead.
    assert out["zh"]["moves"] == [] and out["en"]["moves"] == []


def test_zero_signal_costs_zero_tokens(monkeypatch, tmp_path) -> None:
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
        "trend_7d": [{"day": f"2026-11-{d:02d}", "events": 0} for d in range(1, 8)],
        "forecast": None, "interrupt_causes": None, "completion_streak": None,
        "tool_usage": [], "recommendations": [],
    }
    monkeypatch.setattr("minicc.oracle_trend.build_summary", lambda ws: summary)
    monkeypatch.setattr("minicc.oracle_trend.gather", lambda ws: {"llm_cache": None})

    out = orc.build_trend_insight(config=_config(), workspace=tmp_path, force_refresh=True)
    assert out["verdict"] == "no-signal"
    assert called == []
    assert out["zh"]["narrative"] and out["en"]["narrative"]


def test_model_failure_is_honest_not_raised(monkeypatch, tmp_path) -> None:
    _seed_signal(monkeypatch)

    class _Client:
        def __init__(self, *a, **k):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("provider exploded")

    monkeypatch.setattr("openai.OpenAI", _Client)
    out = orc.build_trend_insight(config=_config(), workspace=tmp_path, force_refresh=True)
    assert out["live"] is False
    assert "RuntimeError" in out["error"]


def test_second_call_rides_the_memo(monkeypatch, tmp_path) -> None:
    _seed_signal(monkeypatch)
    calls = {"n": 0}

    class _Client:
        def __init__(self, *a, **k):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    calls["n"] += 1
                    return _fake_response()

    monkeypatch.setattr("openai.OpenAI", _Client)
    first = orc.build_trend_insight(config=_config(), workspace=tmp_path, force_refresh=True)
    second = orc.build_trend_insight(config=_config(), workspace=tmp_path)
    assert calls["n"] == 1
    assert first["generated_at"] == second["generated_at"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-W", "error"]))
