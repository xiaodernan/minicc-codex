"""M8-T102: each behaviour case must be the pair the grader unpacks.

Measured on ``688ed2d``: the embedded grader runs ``for args, expected in data["cases"]`` and
``for args, expected_type in data.get("raises", [])``. An item that is not a 2-element list of
``[args, name]`` makes the grader raise while unpacking, and ``grade_behavior`` answers
``{'passed': False, 'exit_code': 1}`` - a task no agent could pass, charged to the agent. All 12
shipped tasks are well shaped, so this is construction-reachable rather than live.

The asymmetry from M8-T101 is kept: this is a load-time rule, so ``grade_behavior`` never sees it.
"""

from __future__ import annotations

import copy
import tempfile
from pathlib import Path

import pytest

import minicc.behavior_bench as behavior_bench

REPO_ROOT = Path(__file__).resolve().parent.parent
SOLVABLE = behavior_bench.behavior_tasks()[0]
CODE = "def clamp(value):\n    return max(0, value)\n"


def _task(**grader_extra: object) -> dict:
    task = copy.deepcopy(SOLVABLE)
    task["id"] = "ill-shaped-case-task"
    task["fixture"] = {"solution.py": CODE}
    task["grader"] = {"type": "python_behavior", "function": "clamp",
                      "cases": [[[1], 1]], "raises": []}
    task["grader"].update(grader_extra)
    return task


@pytest.mark.parametrize("cases", [
    pytest.param([[[1], 1, 9]], id="three-element-case"),
    pytest.param([{"args": [1], "expect": 1}], id="dict-case"),
    pytest.param([[1, 1]], id="args-not-a-list"),
])
def test_an_ill_shaped_case_is_refused_naming_its_index(cases: list) -> None:
    with pytest.raises(ValueError) as exc:
        behavior_bench.validate_behavior_task(_task(cases=cases))
    message = str(exc.value)
    assert "cases[0]" in message, message
    assert "ill-shaped-case-task" in message, message


@pytest.mark.parametrize("raises", [
    pytest.param([[["x"]]], id="raise-without-exception-name"),
    pytest.param([{"args": [], "raises": "TypeError"}], id="raise-as-dict"),
])
def test_an_ill_shaped_raise_is_refused_naming_its_index(raises: list) -> None:
    with pytest.raises(ValueError) as exc:
        behavior_bench.validate_behavior_task(_task(cases=[], raises=raises))
    assert "raises[0]" in str(exc.value), exc.value


def test_well_shaped_cases_and_raises_still_load() -> None:
    task = _task(cases=[[[1], 1], [[-1], 0]], raises=[[["x"], "TypeError"]])
    behavior_bench.validate_behavior_task(task)
    assert behavior_bench.fixture_blockers(task) == []


def test_the_grader_does_not_become_a_second_owner_of_the_shape_rule() -> None:
    """Load time checks shapes; grade time must still judge whatever the agent produced."""
    task = _task(cases=[[[1], 1, 9]])
    with pytest.raises(ValueError):
        behavior_bench.validate_behavior_task(task)
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        (workspace / "solution.py").write_text(CODE, encoding="utf-8")
        graded = behavior_bench.grade_behavior(task, workspace)
    assert graded["passed"] is False, graded
    assert not graded.get("grading_refused"), graded


def test_every_shipped_behaviour_task_has_well_shaped_items() -> None:
    tasks = behavior_bench.behavior_tasks()
    assert len(tasks) >= 10, f"only {len(tasks)} tasks read - the census saw nothing"
    offenders = {t["id"]: behavior_bench.fixture_blockers(t) for t in tasks
                 if behavior_bench.fixture_blockers(t)}
    assert offenders == {}, f"shipped behaviour tasks carry ill-shaped items: {offenders}"
