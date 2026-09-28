"""M8-T104: an args value the host cannot encode yields "no result", never a crash.

Measured on ``43472a7``: ``grade_behavior`` builds the grader's stdin with ``json.dumps(grader)``
in the **host** and catches only ``(OSError, subprocess.TimeoutExpired)``, so an ``args`` value
holding a set raised ``TypeError: Object of type set is not JSON serializable`` out of the grader
call - past M8-T94's NO-RESULT machinery, and able to take an entire run down over one malformed
task. Shipped tasks pass only JSON values (12/12 measured), so this is reachable rather than live.

Two doors, two witnesses - the lesson of this batch: the load door refusing a spec is not proof
that the host can no longer escape, because grading is a public entry point reached by other code.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import minicc.behavior_bench as behavior_bench

CODE = "def clamp(value):\n    return max(0, value)\n"

UNENCODABLE = [
    pytest.param([{1, 2}], id="set-in-args"),
    pytest.param([frozenset({1})], id="frozenset-in-args"),
    pytest.param([[{"deep": {1, 2}}]], id="nested-set"),
]


def _task(args: object) -> dict:
    return {"id": "unencodable-args-task",
            "grader": {"type": "python_behavior", "function": "clamp",
                       "cases": [[args, 1]], "raises": []},
            "fixture": {"solution.py": CODE}}


@pytest.mark.parametrize("args", UNENCODABLE)
def test_the_load_door_refuses_args_it_cannot_encode(args: list) -> None:
    with pytest.raises(ValueError) as exc:
        behavior_bench.validate_behavior_task(_task(args))
    message = str(exc.value)
    assert "cases[0]" in message and "JSON" in message, message
    assert "unencodable-args-task" in message, message


@pytest.mark.parametrize("args", UNENCODABLE)
def test_grading_such_a_spec_refuses_instead_of_raising(tmp_path: Path, args: list) -> None:
    """The host-side witness: no TypeError may escape grade_behavior."""
    (tmp_path / "solution.py").write_text(CODE, encoding="utf-8")
    graded = behavior_bench.grade_behavior(_task(args), tmp_path)
    assert graded["passed"] is None, f"the host encode still produced a verdict: {graded}"
    assert graded["grading_refused"] is True, graded
    assert "编码" in graded["refusal"], graded


def test_json_clean_args_still_load_and_grade(tmp_path: Path) -> None:
    task = _task([1])
    behavior_bench.validate_behavior_task(task)
    (tmp_path / "solution.py").write_text(CODE, encoding="utf-8")
    assert behavior_bench.grade_behavior(task, tmp_path)["passed"] is True


def test_the_clearer_shape_refusal_still_comes_first_at_load() -> None:
    task = {"id": "args-not-list", "grader": {"type": "python_behavior", "function": "clamp",
                                             "cases": [[1, 1]], "raises": []},
            "fixture": {"solution.py": CODE}}
    with pytest.raises(ValueError) as exc:
        behavior_bench.validate_behavior_task(task)
    assert "args 为 list" in str(exc.value), exc.value


def test_no_shipped_task_needs_the_new_host_path() -> None:
    """The guard must not become where real tasks land: the census stays clean."""
    tasks = behavior_bench.behavior_tasks()
    assert len(tasks) >= 10, f"only {len(tasks)} tasks read - the census saw nothing"
    offenders = {t["id"]: behavior_bench.spec_blockers(t) for t in tasks
                 if behavior_bench.spec_blockers(t)}
    assert offenders == {}, f"shipped tasks would hit the encode guard: {offenders}"
