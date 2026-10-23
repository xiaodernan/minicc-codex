"""A failed run's answer, and a budget trip's error, must have one home."""

from __future__ import annotations

import ast
import pathlib

from minicc.agent import protocol
from minicc.agent.protocol import budget_exceeded_error, incomplete_answer

REPO = pathlib.Path(__file__).resolve().parents[1]
HOME = "minicc/agent/protocol.py"


def _literals(value: str) -> list[str]:
    hits = []
    for path in sorted((REPO / "minicc").rglob("*.py")):
        tree = ast.parse(path.read_bytes().decode("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == value:
                hits.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}")
    return hits


def test_the_incomplete_answer_is_the_prefix_then_the_reason():
    assert incomplete_answer("boom") == "任务未完成：boom"
    assert incomplete_answer("") == "任务未完成："


def test_the_budget_error_is_one_sentence():
    assert budget_exceeded_error(RuntimeError("x")) == "Agent 预算超限: x"


def test_the_prefix_is_spelled_exactly_once():
    hits = _literals(protocol.INCOMPLETE_ANSWER_PREFIX)
    assert len(hits) == 1, hits
    assert hits[0].startswith("minicc/agent/protocol.py:"), hits


def test_the_budget_prefix_is_spelled_exactly_once():
    hits = _literals(protocol.BUDGET_EXCEEDED_ERROR_PREFIX)
    assert len(hits) == 1, hits
    assert hits[0].startswith("minicc/agent/protocol.py:"), hits


def test_no_other_literal_carries_the_prefix():
    """A near-miss spelling is the drift this batch exists to catch."""
    strays = []
    for path in sorted((REPO / "minicc").rglob("*.py")):
        tree = ast.parse(path.read_bytes().decode("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value.startswith(protocol.INCOMPLETE_ANSWER_PREFIX) and node.value != protocol.INCOMPLETE_ANSWER_PREFIX:
                    strays.append((path.as_posix(), node.lineno, node.value[:40]))
    assert strays == [], strays


def test_the_helpers_are_defined_once():
    for name in ("incomplete_answer", "budget_exceeded_error"):
        definitions = []
        for path in sorted((REPO / "minicc").rglob("*.py")):
            tree = ast.parse(path.read_bytes().decode("utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == name:
                    definitions.append(path.relative_to(REPO).as_posix())
        assert definitions == [HOME], (name, definitions)


def test_the_home_exports_what_it_defines():
    for name in ("INCOMPLETE_ANSWER_PREFIX", "BUDGET_EXCEEDED_ERROR_PREFIX",
                 "incomplete_answer", "budget_exceeded_error"):
        assert name in protocol.__all__, name


def test_the_two_sides_of_one_verdict_agree():
    """The answer a budget trip reports names the error it reports."""
    error = budget_exceeded_error("turns exhausted")
    assert incomplete_answer(error) == "任务未完成：Agent 预算超限: turns exhausted"
