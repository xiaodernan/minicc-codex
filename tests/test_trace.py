"""M8-T829: minicc/trace.py - runtime trace event tests.

Tests for:
- trace_event: builder for runtime trace events
- Fixed key vocabulary shared across all emitters
- detail omitted when None
"""

from __future__ import annotations

import pytest

from minicc.trace import trace_event


def test_trace_event_basic() -> None:
    event = trace_event("name", "ok", "implement", "CODE", "summary")
    assert event["name"] == "name"
    assert event["status"] == "ok"
    assert event["phase"] == "implement"
    assert event["code"] == "CODE"
    assert event["summary"] == "summary"
    assert event["kind"] == "trace"


def test_trace_event_detail_omitted_when_none() -> None:
    event = trace_event("name", "ok", "implement", "CODE", "summary")
    assert "detail" not in event


def test_trace_event_detail_string() -> None:
    event = trace_event("name", "ok", "implement", "CODE", "summary", detail="error text")
    assert event["detail"] == "error text"


def test_trace_event_detail_dict() -> None:
    event = trace_event("name", "ok", "implement", "CODE", "summary", detail={"key": "value"})
    assert event["detail"] == {"key": "value"}


def test_trace_event_explicit_kind() -> None:
    event = trace_event("name", "ok", "implement", "CODE", "summary", kind="metric")
    assert event["kind"] == "metric"
