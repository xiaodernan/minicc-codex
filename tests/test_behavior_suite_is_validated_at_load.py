"""M8-T97: the behaviour suite gets the same load-time door the v2 suite has.

Measured on ``fb44cdd``: the v2 branch of the CLI validates every task before running
(M8-T96), while the behaviour branch called ``behavior_tasks()`` and ran it straight away.
So a behaviour task whose spec judges nothing - no cases and no raises, a typo'd key -
was discovered only at grade time, after the agent had been run.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import minicc.behavior_bench as behavior_bench
from minicc.benchmarks import load_tasks

REPO_ROOT = Path(__file__).resolve().parent.parent
BEHAVIOR_SOURCE = (REPO_ROOT / "minicc" / "behavior_bench.py").read_text(encoding="utf-8")
BENCHMARKS_SOURCE = (REPO_ROOT / "minicc" / "benchmarks.py").read_text(encoding="utf-8")

BAD_SPECS = [
    pytest.param({"type": "python_behavior", "function": "f", "cases": []},
                 id="no-cases-no-raises"),
    pytest.param({"type": "python_behavior", "function": "f",
                  "cases": [[[1], 1]], "casez": []}, id="behaviour-typo-key"),
    pytest.param({"type": "answer_rubric"}, id="rubric-missing-groups"),
    pytest.param({"type": "answer_rubric", "required_any": [["好"]], "cases": []},
                 id="rubric-carries-behaviour-key"),
]
GOOD = {"type": "python_behavior", "function": "f",
        "cases": [[[1, 2], 3]], "raises": [], "preserve_inputs": True}


def _task(spec: dict) -> dict:
    # the fixture must define what the grader imports: an unsolvable task is refused at load
    # time since M8-T101, so these fixtures carry a real solution.py instead of the rule bending
    return {"id": "behaviour-task-needing-a-door", "grader": spec,
            "fixture": {"solution.py": "def f(a, b):\n    return a + b\n"}}


@pytest.mark.parametrize("spec", BAD_SPECS)
def test_the_two_behaviour_doors_refuse_the_same_spec(spec: dict) -> None:
    task = _task(spec)
    with pytest.raises(ValueError) as load_error:
        behavior_bench.validate_behavior_task(task)
    graded = behavior_bench.grade_behavior(task, Path.cwd())
    message = str(load_error.value)
    assert task["id"] in message, message
    assert graded["passed"] is None, f"the loader refused but the grader judged: {graded}"
    assert graded["grading_refused"] is True, graded
    phrase = message.split("无法判分: ", 1)[1]
    assert phrase in graded["refusal"], (message, graded)


def test_a_scoreable_behaviour_task_passes_both_doors(tmp_path: Path) -> None:
    task = {"id": "ok-task", "grader": GOOD,
            "fixture": {"solution.py": "def f(a, b):\n    return a + b\n"}}
    behavior_bench.validate_behavior_task(task)
    (tmp_path / "solution.py").write_text("def f(a, b):\n    return a + b\n", encoding="utf-8")
    graded = behavior_bench.grade_behavior(task, tmp_path)
    assert graded["passed"] is True, graded
    assert not graded.get("grading_refused"), graded


def test_an_unknown_grader_type_is_named_by_the_door() -> None:
    with pytest.raises(ValueError) as exc:
        behavior_bench.validate_behavior_task({"id": "x", "grader": {"type": "magic"}})
    assert "magic" in str(exc.value), exc.value


def test_the_owner_of_the_rule_is_one_function_per_domain() -> None:
    """Each wording lives in exactly one place, so the doors cannot drift apart."""
    tree = ast.parse(BEHAVIOR_SOURCE)
    homes: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Constant) and isinstance(inner.value, str) \
                    and "nothing was checked" in inner.value:
                homes.setdefault("nothing was checked", []).append(node.name)
            if isinstance(inner, ast.Constant) and isinstance(inner.value, str) \
                    and "keys nobody reads" in inner.value:
                homes.setdefault("keys nobody reads", []).append(node.name)
    for phrase, functions in homes.items():
        assert set(functions) == {"spec_blockers"}, (phrase, sorted(functions))


def test_the_declared_behaviour_types_match_what_the_grader_dispatches() -> None:
    tree = ast.parse(BEHAVIOR_SOURCE)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "grade_behavior")
    dispatched = {node.comparators[0].value for node in ast.walk(fn)
                  if isinstance(node, ast.Compare) and len(node.ops) == 1
                  and isinstance(node.ops[0], (ast.Eq, ast.NotEq))
                  and isinstance(node.left, ast.Call) and isinstance(node.left.func, ast.Attribute)
                  and node.left.func.attr == "get" and isinstance(node.comparators[0], ast.Constant)}
    # both spellings count: the rubric branch tests equality, the behaviour branch tests
    # inequality before it; reading only one of them left a blind spot in this gate.
    assert dispatched == set(behavior_bench.BEHAVIOR_GRADER_TYPES), (
        f"grade_behavior dispatches {sorted(dispatched)} but the door declares "
        f"{sorted(behavior_bench.BEHAVIOR_GRADER_TYPES)}"
    )


def test_the_runner_opens_the_behaviour_door() -> None:
    """A validator nobody calls is a comment, not a gate."""
    tree = ast.parse(BENCHMARKS_SOURCE)
    callers = {node.func.id for node in ast.walk(tree)
               if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
               and node.func.id == "validate_behavior_task"}
    assert callers, "benchmarks.py never calls validate_behavior_task"
    runner = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                  and any(isinstance(inner, ast.Call)
                          and isinstance(inner.func, ast.Name)
                          and inner.func.id == "validate_behavior_task"
                          for inner in ast.walk(n)))
    source = ast.unparse(runner)
    assert "behavior_tasks()" in source, "the door is not on the behaviour suite's path"


def test_every_shipped_behaviour_task_passes_the_new_door() -> None:
    """The door must not reject the suite it protects."""
    tasks = behavior_bench.behavior_tasks()
    assert len(tasks) >= 10, f"only {len(tasks)} behaviour tasks read - the census saw nothing"
    offenders = []
    for task in tasks:
        try:
            behavior_bench.validate_behavior_task(task)
        except ValueError as exc:
            offenders.append(f"{task['id']}: {exc}")
    assert offenders == [], offenders
    legacy = load_tasks(REPO_ROOT / "benchmarks" / "tasks.json")
    assert len(legacy) >= 20, f"legacy suite reads {len(legacy)} tasks"
