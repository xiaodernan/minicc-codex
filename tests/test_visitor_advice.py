# M8-T1292 — model-free optimisation advice must stay tied to measured facts.

from __future__ import annotations

import pytest

from minicc.visitor_advice import build_visitor_advice


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
        "last_views": [{"view": "landing", "count": 3, "share": 0.6}],
        "transitions": [{"from": "landing", "to": "manual", "count": 4, "share": 0.4}],
        "how_to": "node scripts/behavior_sim.mjs --runs 6",
    }
    base.update(overrides)
    return base


def _actions(payload):
    return payload["zh"]["moves"]


def test_empty_log_is_honest_and_offers_no_fake_fix():
    payload = build_visitor_advice({"live": False, "total": 0, "how_to": "run the probe"})
    assert payload["live"] is False
    assert payload["verdict"] == "no-signal"
    assert payload["model_free"] is True
    assert payload["zh"]["moves"] == []
    assert payload["en"]["moves"] == []
    assert "run the probe" in payload["en"]["how_to"]


def test_high_boot_names_the_startup_cost_with_its_real_reading():
    payload = build_visitor_advice(_report(median_boot_ms=1600))
    assert payload["focus"] == "time-to-clickable"
    move = _actions(payload)[0]
    assert "1600 ms" in move["evidence"]
    assert "web/index.html" in move["zh"]["action"]
    assert "behavior_sim.mjs" in move["zh"]["accept"]


def test_just_below_threshold_does_not_invent_an_urgent_fix():
    payload = build_visitor_advice(_report(median_boot_ms=1199, rage_journeys=2, page_errors=0))
    assert payload["focus"] != "time-to-clickable"
    assert not any("1600" in m["evidence"] for m in _actions(payload))


def test_bounce_names_navigation_and_the_onboarding_door():
    payload = build_visitor_advice(_report(median_boot_ms=900, rage_journeys=1,
                                          last_views=[]))
    assert payload["focus"] == "navigation"
    assert any("onboarding.js" in m["zh"]["action"] for m in _actions(payload))


def test_rage_sessions_and_page_errors_are_feedback_evidence():
    payload = build_visitor_advice(_report(median_boot_ms=900, rage_journeys=5,
                                          page_errors=2, last_views=[]))
    assert payload["focus"] == "feedback"
    evidence = " ".join(m["evidence"] for m in _actions(payload))
    assert "rage_sessions=5/15" in evidence
    assert "page_errors=2" in evidence
    assert any(".nav-item" in m["zh"]["action"] for m in _actions(payload))


def test_dominant_exit_points_at_the_real_panel_not_an_invented_module():
    payload = build_visitor_advice(_report(median_boot_ms=900, rage_journeys=0,
                                          last_views=[{"view": "atlas", "count": 6, "share": 0.6}]))
    move = next(m for m in _actions(payload) if "atlas" in m["evidence"])
    assert "web/src/panels/atlas.js" in move["zh"]["action"]


def test_unknown_exit_view_falls_back_to_a_selector_never_a_guessed_path():
    payload = build_visitor_advice(_report(median_boot_ms=900, rage_journeys=0,
                                          last_views=[{"view": "imaginary", "count": 6, "share": 0.6}]))
    move = next(m for m in _actions(payload) if "imaginary" in m["evidence"])
    assert ".nav-item" in move["zh"]["action"]
    assert "imaginary.js" not in move["zh"]["action"]


def test_short_dwell_without_bounce_gets_a_content_move():
    payload = build_visitor_advice(_report(median_boot_ms=900, bounce_rate=0.05,
                                          median_dwell_ms=2300, rage_journeys=0,
                                          last_views=[]))
    assert payload["focus"] == "content"
    assert any("almanac.js" in m["zh"]["action"] for m in _actions(payload))


def test_moves_are_bounded_and_bilingual():
    payload = build_visitor_advice(_report())
    assert len(_actions(payload)) <= 4
    assert len(payload["en"]["moves"]) == len(_actions(payload))
    for move in _actions(payload):
        assert move["zh"]["action"] and move["zh"]["accept"]
        assert len(move["zh"]["action"]) <= 180
        assert move["en"]["action"] and move["en"]["accept"]
        assert len(move["en"]["action"]) <= 240


def test_thin_sample_is_labelled_in_both_languages():
    payload = build_visitor_advice(_report(confidence="thin"))
    assert "偏薄" in payload["zh"]["narrative"]
    assert "Thin sample" in payload["en"]["narrative"]


def test_narrative_quotes_only_numbers_present_in_the_report():
    report = _report()
    payload = build_visitor_advice(report)
    for value in [str(report["total"]), "33%", "1057 ms", "3", "0"]:
        assert value in payload["zh"]["narrative"]
    assert "undefined" not in payload["zh"]["narrative"]
    assert "NaN" not in payload["en"]["narrative"]


def test_broken_input_never_raises():
    for value in [None, [], {}, {"live": True, "total": 0}]:
        payload = build_visitor_advice(value)
        assert payload["live"] is False
        assert payload["model_free"] is True
