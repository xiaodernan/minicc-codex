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


def test_behavior_load_door_accepts_all_shipped_behaviour_tasks() -> None:
    """The census runs the behavior load door, not a named helper.

    Measured at 第九十批: mutation arm E2 moved the shape rule from ``fixture_blockers`` into
    ``spec_blockers`` and the previous version of this census stayed green while checking
    nothing about shape - it read a function that no longer held the rule. A census keyed to
    a helper's *name* reports vacuity as a pass. Renamed from
    ``test_every_shipped_behaviour_task_has_well_shaped_items``, which kept claiming to census
    the *shape of items* after 第九十批 had pointed it at the door (第九十九批, M8-T113 record).

    Division of labor, measured rather than asserted (``_probe113.py``, AST over every
    shipped-population census - it reads which rule each one calls and which population it
    feeds that rule). There are **three** parties, not two, and the door is the one with two
    owners:

    * door - ``validate_behavior_task`` over ``behavior_bench.behavior_tasks()``: this test,
      and ``test_behavior_suite_is_validated_at_load.py::test_every_shipped_behaviour_task_passes_the_new_door``.
      Same rule, same population: one gate written twice. Whether to merge them is the owner's
      call (第九十五批 §8-2 deferred it until the measurement existed; it now exists).
    * host encoding path - ``spec_blockers`` over the behaviour suite: the companion is
      ``test_behavior_args_that_cannot_be_encoded_are_no_result.py::test_no_shipped_task_needs_the_new_host_path``.
    * host write point - ``require_writable_fixture`` over all three suites:
      ``test_a_fixture_must_be_text_the_workspace_can_hold.py::test_no_shipped_task_needs_the_new_rule``.

    An earlier draft of this docstring named the second of those
    ``test_host_encoding_path_accepts_all_shipped_fixtures`` while describing the third - a
    census that exists nowhere, fused from one gate's concept and another's population. That
    is why the names above are spelled out in full.
    """
    tasks = behavior_bench.behavior_tasks()
    assert len(tasks) >= 10, f"only {len(tasks)} tasks read - the census saw nothing"
    offenders: dict[str, str] = {}
    for task in tasks:
        try:
            behavior_bench.validate_behavior_task(task)
        except ValueError as exc:
            offenders[task["id"]] = str(exc)
    assert offenders == {}, f"shipped behaviour tasks are refused by their own load door: {offenders}"
