"""M8-T94: a behavior spec that names nothing to check has no verdict to give.

Measured on ``756b24d`` by calling the shipped producer:

    grade_behavior({'type': 'answer_rubric', 'required_any': []})
        -> {'passed': False, 'grader_type': 'answer_rubric', 'case_count': 0}
    grade_behavior({'type': 'python_behavior', 'function': 'f', 'cases': []})   # real solution.py
        -> {'passed': True, 'grader_type': 'python_behavior', 'case_count': 0, 'exit_code': 0}

One empty spec blamed the agent for a blank rubric; the other passed an untouched
workspace because zero cases still prints the completion marker for zero. They are the
same two failures M8-T87/M8-T90 already closed in the contract graders, arriving through
the third and fourth grader types. A mistyped spec key (``casez`` for ``cases``) was
simply ignored, exactly the M8-T92 shape.

The vocabulary is the one M8-T92 derived from the shipped grader source, so no list is
copied here either.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import minicc.bench_tasks as bench_tasks
import minicc.behavior_bench as behavior_bench
from minicc.benchmarks import build_report

REPO_ROOT = Path(__file__).resolve().parent.parent
NO_RESULT_KEYS = {"passed", "grader_type", "grading_refused", "refusal"}


@pytest.fixture
def solution(tmp_path: Path) -> Path:
    (tmp_path / "solution.py").write_text("def f(a, b):\n    return a + b\n", encoding="utf-8")
    return tmp_path


def _grade(spec: dict, tmp_path: Path, answer: str = "") -> dict:
    return behavior_bench.grade_behavior({"grader": spec}, tmp_path, answer)


@pytest.mark.parametrize("spec,expected_key", [
    ({"type": "answer_rubric", "required_any": []}, "required_any"),
    ({"type": "answer_rubric"}, "required_any"),
    ({"type": "python_behavior", "function": "f", "cases": []}, "nothing was checked"),
    ({"type": "python_behavior", "function": "f", "cases": [], "raises": []}, "nothing was checked"),
    ({"type": "python_behavior", "function": "f", "cases": [[[1, 2], 3]], "casez": []}, "casez"),
])
def test_a_behavior_spec_that_checks_nothing_has_no_verdict(
    tmp_path: Path, solution: Path, spec: dict, expected_key: str
) -> None:
    graded = _grade(spec, tmp_path)
    assert graded["passed"] is None, f"an empty behavior spec produced a verdict: {graded}"
    assert graded["grading_refused"] is True, graded
    assert expected_key in graded["refusal"], graded
    assert set(graded) == NO_RESULT_KEYS, graded


def test_a_real_behavior_grader_still_reaches_a_verdict(tmp_path: Path, solution: Path) -> None:
    """The refusals must not swallow the 12 shipped-style specs."""
    graded = _grade({"type": "python_behavior", "function": "f",
                     "cases": [[[1, 2], 3], [[-1, -1], -2]],
                     "raises": [[[1, "x"], "TypeError"]], "preserve_inputs": True}, tmp_path)
    assert graded["passed"] is True, graded
    assert graded["case_count"] == 3, graded
    assert not graded.get("grading_refused"), graded


def test_a_real_rubric_still_reaches_a_verdict(tmp_path: Path) -> None:
    graded = _grade({"type": "answer_rubric", "required_any": [["很好", "good"], ["完成"]]},
                    tmp_path, answer="很好，任务完成。")
    assert graded["passed"] is True, graded
    assert graded["case_count"] == 2, graded


def test_the_vocabulary_is_shared_with_the_contract_graders_not_recopied(tmp_path: Path) -> None:
    """One reader walk serves all three embedded scripts, so no second list exists."""
    vocab = bench_tasks.grader_vocabulary("python_behavior", behavior_bench._GRADER)
    assert set(vocab["spec"]) >= {"function", "cases", "raises", "preserve_inputs"}, vocab
    # The script names its stdin payload "data", not "spec": a walk keyed only on
    # "spec" would return an empty vocabulary and reject every shipped task.
    assert "function" in vocab["spec"], vocab


def test_every_shipped_behavior_task_is_verifiable() -> None:
    raw = json.loads((REPO_ROOT / "benchmarks" / "behavior-tasks.json").read_text(encoding="utf-8"))
    tasks = raw if isinstance(raw, list) else raw.get("tasks", [])
    assert len(tasks) >= 10, f"only {len(tasks)} behavior tasks read - the census saw nothing"
    offenders = []
    for task in tasks:
        spec = task.get("grader") or {}
        dead = bench_tasks.unverifiable_spec_keys("python_behavior", behavior_bench._GRADER, spec)
        if dead or (len(spec.get("cases") or []) + len(spec.get("raises") or [])) == 0:
            offenders.append((task.get("id"), dead))
    assert offenders == [], f"shipped behavior specs are not verifiable: {offenders}"


def test_a_refused_behavior_spec_reaches_the_report_as_a_refusal(tmp_path: Path, solution: Path) -> None:
    graded = _grade({"type": "python_behavior", "function": "f", "cases": []}, tmp_path)
    task = {"id": "empty-behavior", "category": "code", "prompt": "p",
            "grader": {"type": "python_behavior", "function": "f", "cases": []}}
    row = {"task_id": "empty-behavior", "category": "code", "status": "completed",
           "claimed_complete": True, **graded}
    metrics = build_report([task], [row])["metrics"]
    assert metrics["grading_refusal_count"] == 1, metrics
    assert metrics["gradable_task_count"] == 0, metrics
