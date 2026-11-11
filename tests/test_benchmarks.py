"""M8-T788: minicc/benchmarks.py - benchmark module tests.

Tests for pure functions in benchmarks module:
- _review_rounds: bounded digest of review rounds
- _quantile: quantile calculation
- _declared_grader_type: grader type detection
- _oracle_says_pass: oracle pass/fail decision
"""

from __future__ import annotations

import pytest
from pathlib import Path

from minicc.benchmarks import (
    _review_rounds,
    _quantile,
    _declared_grader_type,
    _oracle_says_pass,
    RETRIEVAL_RECALL_FLOOR,
)


# ============================================================================
# _review_rounds
# ============================================================================

def test_review_rounds_empty() -> None:
    assert _review_rounds([]) == []
    assert _review_rounds(None) == []


def test_review_rounds_filters_completion_judge() -> None:
    events = [
        {"name": "completion_judge", "detail": {"status": "ok", "rationale": "good", "missing": []}},
        {"name": "other_event", "detail": {"status": "ok"}},
        {"name": "completion_judge", "detail": {"status": "failed", "rationale": "bad", "missing": ["x", "y"]}},
    ]
    result = _review_rounds(events)
    assert len(result) == 2
    assert result[0]["code"] == ""
    assert result[0]["status"] == "ok"
    assert result[0]["rationale"] == "good"
    assert result[1]["code"] == ""
    assert result[1]["status"] == "failed"
    assert result[1]["rationale"] == "bad"
    assert result[1]["missing"] == ["x", "y"]


def test_review_rounds_truncates_to_8() -> None:
    events = [
        {"name": "completion_judge", "detail": {"status": f"status_{i}", "rationale": f"rationale_{i}", "missing": []}}
        for i in range(10)
    ]
    result = _review_rounds(events)
    assert len(result) == 8
    assert result[0]["rationale"] == "rationale_2"
    assert result[-1]["rationale"] == "rationale_9"


# ============================================================================
# _quantile
# ============================================================================

def test_quantile_empty() -> None:
    assert _quantile([], 0.5) is None


def test_quantile_single() -> None:
    assert _quantile([5], 0.5) == 5


def test_quantile_median() -> None:
    assert _quantile([1, 2, 3, 4, 5], 0.5) == 3


def test_quantile_lower_quartile() -> None:
    assert _quantile([1, 2, 3, 4], 0.25) == 1.75


def test_quantile_upper_quartile() -> None:
    assert _quantile([1, 2, 3, 4], 0.75) == 3.25


# ============================================================================
# _declared_grader_type
# ============================================================================

def test_declared_grader_type_known() -> None:
    assert _declared_grader_type({"grader": {"type": "pytest"}}) == "pytest"
    assert _declared_grader_type({"grader": {"type": "mypy"}}) == "mypy"
    assert _declared_grader_type({"grader": {"type": "ruff"}}) == "ruff"


def test_declared_grader_type_unknown() -> None:
    assert _declared_grader_type({"grader": {"type": "unknown_tool"}}) == "unknown_tool"


def test_declared_grader_type_no_grader() -> None:
    assert _declared_grader_type({}) == "ungraded"


# ============================================================================
# _oracle_says_pass
# ============================================================================

def test_oracle_says_pass_true() -> None:
    assert _oracle_says_pass({"objective_oracle": {"passed": True, "case_count": 1}}) is True
    assert _oracle_says_pass({"objective_oracle": {"passed": True, "case_count": 5}}) is True


def test_oracle_says_pass_false() -> None:
    assert _oracle_says_pass({"objective_oracle": {"passed": False, "case_count": 1}}) is False
    assert _oracle_says_pass({"objective_oracle": {"passed": True, "case_count": 0}}) is False


def test_oracle_says_pass_missing() -> None:
    assert _oracle_says_pass({}) is False
    assert _oracle_says_pass({"objective_oracle": {"passed": False}}) is False


# ============================================================================
# Constants
# ============================================================================

def test_retrieval_recall_floor() -> None:
    assert RETRIEVAL_RECALL_FLOOR == 0.6
