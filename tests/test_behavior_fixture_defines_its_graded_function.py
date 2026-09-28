"""M8-T101: a behaviour task's own fixture must define the function it grades.

Measured on ``290037e``: all 12 generated behaviour tasks do define it, and when the graded name
is not bound the embedded grader's ``getattr`` dies and ``grade_behavior`` answers
``passed=False`` - the grader's own failure booked as the agent's false completion, on a task no
agent could pass. So the load door reads the fixture.

The line this batch draws on purpose: an *agent* that deletes the function has really failed and
must still get a verdict, which is why only ``validate_behavior_task`` consults the fixture.
"""

from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

import minicc.behavior_bench as behavior_bench

REPO_ROOT = Path(__file__).resolve().parent.parent
SOLVABLE = behavior_bench.behavior_tasks()[0]


def _task(function: str = "nope", fixture: object = None) -> dict:
    task = copy.deepcopy(SOLVABLE)
    task["id"] = "unsolvable-task-needs-a-door"
    task["grader"] = {**task["grader"], "function": function}
    if fixture is not None:
        task["fixture"] = fixture if isinstance(fixture, dict) else {"solution.py": fixture}
    return task


@pytest.mark.parametrize("code", [
    pytest.param("def other():\n    return 1\n", id="function-never-bound"),
    pytest.param("def (\n", id="fixture-not-parseable"),
    pytest.param(None, id="no-solution-file"),
])
def test_an_ungradable_fixture_is_refused_before_any_agent_runs(code: object) -> None:
    fixture = {"README.md": "x"} if code is None else {"solution.py": code}
    with pytest.raises(ValueError) as exc:
        behavior_bench.validate_behavior_task(_task(fixture=fixture))
    message = str(exc.value)
    assert "unsolvable-task-needs-a-door" in message, message
    assert "solution.py" in message or "nope" in message, message


def test_a_bound_name_counts_as_defined() -> None:
    """The door asks what the grader can import, not only what a ``def`` binds.

    Only that claim is tested: whether a partial-bound callable then behaves under the grader's
    type-strict comparison is a separate question I had not measured, so it is not asserted here.
    """
    code = "import functools\nclamp = functools.partial(max, 0)\n"
    assert "clamp" in behavior_bench.defined_names(code)
    task = _task(function="clamp", fixture={"solution.py": code})
    behavior_bench.validate_behavior_task(task)
    assert behavior_bench.fixture_blockers(task) == []


def test_an_agent_that_deletes_the_function_still_gets_a_verdict(tmp_path: Path) -> None:
    """The distinction this batch is about: unsolvable is a task fault, missing is an agent fault."""
    task = _task(function="clamp", fixture={"solution.py": "def clamp(v):\n    return v\n"})
    behavior_bench.validate_behavior_task(task)
    (tmp_path / "solution.py").write_text("def unrelated():\n    return 1\n", encoding="utf-8")
    graded = behavior_bench.grade_behavior(task, tmp_path)
    assert graded["passed"] is False, graded
    assert not graded.get("grading_refused"), graded


def test_every_shipped_behaviour_task_defines_its_graded_function() -> None:
    tasks = behavior_bench.behavior_tasks()
    assert len(tasks) >= 10, f"only {len(tasks)} tasks read - the census saw nothing"
    offenders = [t["id"] for t in tasks if behavior_bench.fixture_blockers(t)]
    assert offenders == [], f"shipped tasks are unsolvable as written: {offenders}"


def test_only_the_load_door_consults_the_fixture_rule() -> None:
    tree = ast.parse((REPO_ROOT / "minicc" / "behavior_bench.py").read_text(encoding="utf-8"))
    validator = next(n for n in ast.walk(tree)
                     if isinstance(n, ast.FunctionDef) and n.name == "validate_behavior_task")
    called = {c.func.id for c in ast.walk(validator)
              if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    assert {"spec_blockers", "fixture_blockers"} <= called, sorted(called)
    grader = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "grade_behavior")
    grader_calls = {c.func.id for c in ast.walk(grader)
                    if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    assert "fixture_blockers" not in grader_calls, (
        "grade time must not refuse an agent that deleted the function - that is a failure"
    )
