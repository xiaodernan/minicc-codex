"""M8-T1289b — the visitor oracle reads a measured sample, never an invented one.

Truth invariants pinned here: an empty log costs zero tokens; the prompt carries
the real aggregates (bounce rate, boot median, rage sessions, exit views) and the
view names a fix can actually point at; a focus outside the vocabulary fails
closed; an unparsable answer or a model failure is an honest ``live: False``; the
memo serves the same sample without a second call, and a new sample invalidates
it instead of serving yesterday's opinion.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import minicc.oracle_visitors as orc
from minicc.oracle_common import default_cache


def _report(**overrides):
    base = {
        "live": True,
        "total": 15,
        "bounce_rate": 0.333,
        "median_dwell_ms": 7908,
        "median_boot_ms": 1057,
        "rage_journeys": 3,
        "page_errors": 0,
        "confidence": "usable",
        "window": {"start": "2026-11-22T05:25:27.072Z", "end": "2026-11-22T05:28:38.811Z"},
        "personas": [
            {"id": "impatient", "runs": 3, "bounce_rate": 1.0, "median_dwell_ms": 2929,
             "mean_clicks": 0.0, "top_exit": "landing"},
            {"id": "power", "runs": 3, "bounce_rate": 0.0, "median_dwell_ms": 6052,
             "mean_clicks": 3.0, "top_exit": ""},
        ],
        "last_views": [{"view": "landing", "count": 3, "share": 0.6},
                       {"view": "dockyard", "count": 1, "share": 0.2}],
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _clear_cache():
    default_cache.set(orc._CACHE_KEY, None, ttl=0)
    yield
    default_cache.set(orc._CACHE_KEY, None, ttl=0)


def _config():
    return SimpleNamespace(model="test-model", base_url="https://example.invalid/v1",
                           api_key="test-key", prompt_cache_key="", timeout=60)


def _payload(**overrides):
    base = {
        "focus": "navigation",
        "zh": {"narrative": "15 段旅程三成跳出，退出集中在 landing。",
               "moves": ["给 .nav-item 加首屏高亮（验收：3 秒内能指出下一步）"]},
        "en": {"narrative": "A third of 15 sessions bounced, exits cluster on landing.",
               "moves": ["Highlight .nav-item on first paint (check: next step visible in 3s)"]},
    }
    base.update(overrides)
    return base


def _fake(monkeypatch, *, payload=None, text=None, calls=None, error=None):
    def fake_call_model(*, config, prompt, max_tokens=280, temperature=0.2):
        if calls is not None:
            calls.append(prompt)
        if error is not None:
            raise error
        raw = text if text is not None else json.dumps(payload or _payload(), ensure_ascii=False)
        return {
            "text": raw,
            "model": "gpt-6.2-sol",
            "usage": {"prompt_tokens": 1200, "completion_tokens": 180, "cached_tokens": 900},
        }

    monkeypatch.setattr(orc, "call_model", fake_call_model)


def test_empty_log_costs_zero_tokens(monkeypatch, tmp_path) -> None:
    calls: list[str] = []
    _fake(monkeypatch, calls=calls)
    out = orc.build_visitor_insight(config=_config(), workspace=tmp_path,
                                     report=_report(live=False, total=0, personas=[], last_views=[]))
    assert calls == []
    assert out["live"] is True
    assert out["verdict"] == "no-signal"
    assert out["focus"] == "unknown"
    assert out["zh"]["narrative"] and out["en"]["narrative"]
    assert out["zh"]["moves"] == []


def test_prompt_carries_the_measured_sample(monkeypatch, tmp_path) -> None:
    calls: list[str] = []
    _fake(monkeypatch, calls=calls)
    orc.build_visitor_insight(config=_config(), workspace=tmp_path, report=_report())
    prompt = calls[0]
    for marker in ("bounce_rate", "median_boot_ms", "rage_sessions", "exit_views", "landing", "known_views"):
        assert marker in prompt
    # the actual readings, not placeholders
    assert "7908" in prompt and "1057" in prompt and "0.333" in prompt


def test_reading_is_bilingual_and_focus_is_bounded(monkeypatch, tmp_path) -> None:
    _fake(monkeypatch)
    out = orc.build_visitor_insight(config=_config(), workspace=tmp_path, report=_report())
    assert out["live"] is True
    assert out["verdict"] == "model-visitors"
    assert out["focus"] == "navigation"
    assert out["zh"]["moves"] and out["en"]["moves"]
    assert out["sample"]["total"] == 15
    assert out["usage"]["cached_tokens"] == 900


def test_focus_outside_the_vocabulary_fails_closed(monkeypatch, tmp_path) -> None:
    _fake(monkeypatch, payload=_payload(focus="make-it-prettier"))
    out = orc.build_visitor_insight(config=_config(), workspace=tmp_path, report=_report())
    assert out["live"] is True
    assert out["focus"] == "unknown"
    assert out["zh"]["narrative"]  # the words survive even when the badge does not


def test_unparsable_answer_is_an_honest_outage(monkeypatch, tmp_path) -> None:
    _fake(monkeypatch, text="I think the page is fine, honestly.")
    out = orc.build_visitor_insight(config=_config(), workspace=tmp_path, report=_report())
    assert out["live"] is False
    assert out["verdict"] == "unparsable-model-answer"
    assert out["zh"]["narrative"] == ""


def test_model_failure_never_raises(monkeypatch, tmp_path) -> None:
    _fake(monkeypatch, error=RuntimeError("gateway down"))
    out = orc.build_visitor_insight(config=_config(), workspace=tmp_path, report=_report())
    assert out["live"] is False
    assert out["verdict"] == "model-unavailable"
    assert "gateway down" in out["error"]


def test_memo_serves_the_same_sample_without_a_second_call(monkeypatch, tmp_path) -> None:
    calls: list[str] = []
    _fake(monkeypatch, calls=calls)
    first = orc.build_visitor_insight(config=_config(), workspace=tmp_path, report=_report())
    second = orc.build_visitor_insight(config=_config(), workspace=tmp_path, report=_report())
    assert len(calls) == 1
    assert second["signature"] == first["signature"]


def test_a_new_sample_invalidates_the_memo(monkeypatch, tmp_path) -> None:
    calls: list[str] = []
    _fake(monkeypatch, calls=calls)
    orc.build_visitor_insight(config=_config(), workspace=tmp_path, report=_report())
    newer = _report(window={"start": "2026-11-22T06:00:00.000Z", "end": "2026-11-22T06:05:00.000Z"})
    orc.build_visitor_insight(config=_config(), workspace=tmp_path, report=newer)
    assert len(calls) == 2
