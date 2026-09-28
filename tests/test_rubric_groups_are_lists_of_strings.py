"""M8-T103: a rubric group must be a list of strings, never a bare string.

Measured on ``f2d9e4d``: the rubric evaluates ``any(str(term).casefold() in folded for term in
group)``, so ``[["好"], "完成"]`` scored ``passed=True, case_count=2`` - the bare string was
iterated character by character and a single shared character satisfied the group. Empty groups,
non-string members and dict groups never matched at all, i.e. an unsatisfiable requirement
charged to the agent. This is the first shape in the arc that became **looser** rather than
crashing, which is exactly why it needs a door: nothing else announces it.
"""

from __future__ import annotations

import pytest

import minicc.behavior_bench as behavior_bench

GOOD = {"type": "answer_rubric", "required_any": [["很好", "good"], ["完成"]]}
ANSWER = "这个实现很好，任务完成"

ILL_SHAPED = [
    pytest.param([["好"], "完成"], "required_any[1]", id="bare-string-group-widens"),
    pytest.param([[]], "required_any[0]", id="empty-group-never-passes"),
    pytest.param([[123]], "required_any[0]", id="non-string-member"),
    pytest.param([{"term": "好"}], "required_any[0]", id="dict-group"),
    pytest.param([["   "]], "required_any[0]", id="blank-member"),
]


@pytest.mark.parametrize("required_any,phrase", ILL_SHAPED)
def test_an_ill_shaped_rubric_is_refused_naming_its_group(required_any, phrase) -> None:
    task = {"id": "ill-shaped-rubric-task",
            "grader": {"type": "answer_rubric", "required_any": required_any}}
    with pytest.raises(ValueError) as exc:
        behavior_bench.validate_behavior_task(task)
    assert phrase in str(exc.value), exc.value
    assert "ill-shaped-rubric-task" in str(exc.value), exc.value


@pytest.mark.parametrize("required_any,phrase", ILL_SHAPED)
def test_the_grader_refuses_the_same_shape_it_was_about_to_loosen(required_any, phrase) -> None:
    graded = behavior_bench.grade_answer_rubric(
        {"grader": {"type": "answer_rubric", "required_any": required_any}}, answer=ANSWER)
    assert graded["passed"] is None, f"a loose shape produced a verdict: {graded}"
    assert graded["grading_refused"] is True, graded


def test_a_well_shaped_rubric_still_grades_both_ways() -> None:
    task = {"id": "good-rubric", "grader": GOOD}
    behavior_bench.validate_behavior_task(task)
    assert behavior_bench.grade_answer_rubric(task, answer=ANSWER)["passed"] is True
    assert behavior_bench.grade_answer_rubric(task, answer="不相关的回答")["passed"] is False


def test_a_single_shared_character_no_longer_satisfies_a_group() -> None:
    """The exact regression the bare-string shape allowed: one character === the word."""
    with pytest.raises(ValueError):
        behavior_bench.validate_behavior_task({"id": "x", "grader": {
            "type": "answer_rubric", "required_any": ["完成"]}})
    task = {"grader": {"type": "answer_rubric", "required_any": [["完成"]]}}
    assert behavior_bench.grade_answer_rubric(task, answer="完")["passed"] is False
