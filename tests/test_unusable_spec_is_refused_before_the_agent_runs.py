"""M8-T96: "this spec cannot be judged" has one owner and two doors.

Measured on ``e6aceb9``: ``validate_task`` accepted ``files: []``, ``files: ['a.txt']``,
``command: ''`` and a spec carrying ``expct_exit``. Those specs are refused at grade time
since M8-T90..M8-T94 - after the agent has already been run and paid for a task file that
could never be scored. The loader now asks the same question of the same function, so the
two doors cannot hold different ideas of "unusable".
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import minicc.benchmarks as benchmarks
import minicc.bench_tasks as bench_tasks
from minicc.benchmarks import load_tasks

REPO_ROOT = Path(__file__).resolve().parent.parent
BASE = {"id": "task-id-must-be-named", "category": "c", "prompt": "回答任意内容。", "max_minutes": 5,
        "fixture": {"a.txt": "x"}}

UNUSABLE = [
    ({"type": "file_contract", "files": []}, "no files"),
    ({"type": "file_contract", "files": ["a.txt"]}, "non-empty string path"),
    ({"type": "command_contract", "command": ""}, "no command to run"),
    ({"type": "command_contract", "command": "x", "expct_exit": 1}, "keys nobody reads"),
]
USABLE = {"type": "file_contract", "files": [{"path": "a.txt", "contains": "x"}]}


def _task(spec: dict) -> dict:
    return {**BASE, "grader": spec}


@pytest.mark.parametrize("spec,phrase", UNUSABLE,
                         ids=[f"blocker{i}-{phrase}" for i, (_s, phrase) in enumerate(UNUSABLE)])
def test_the_loader_and_the_grader_refuse_the_same_spec_the_same_way(
    tmp_path: Path, spec: dict, phrase: str
) -> None:
    with pytest.raises(ValueError) as load_error:
        bench_tasks.validate_task(_task(spec))
    graded = bench_tasks.grade_v2(_task(spec), tmp_path, grader_dir=tmp_path / "g")

    assert phrase in str(load_error.value), load_error.value
    assert graded["passed"] is None, f"the loader refused but the grader judged: {graded}"
    assert phrase in graded["refusal"], (load_error.value, graded)
    assert BASE["id"] in str(load_error.value), (
        "a load-time refusal that does not name the task id is unactionable in a 24-task file; "
        "the id here is deliberately long because a one-letter id appears in any text"
    )


def test_a_scoreable_spec_passes_both_doors(tmp_path: Path) -> None:
    bench_tasks.validate_task(_task(USABLE))
    graded = bench_tasks.grade_v2(_task(USABLE), tmp_path, grader_dir=tmp_path / "g")
    assert graded.get("grading_refused") is not True, graded


def test_the_script_table_covers_exactly_the_shipped_grader_types() -> None:
    """A new contract type without a script would silently skip the vocabulary check."""
    assert set(bench_tasks.GRADER_SCRIPTS) == set(bench_tasks.GRADER_TYPES), (
        f"GRADER_TYPES={sorted(bench_tasks.GRADER_TYPES)} but scripts cover "
        f"{sorted(bench_tasks.GRADER_SCRIPTS)}"
    )
    for grader_type, constant in bench_tasks.GRADER_SCRIPTS.items():
        value = getattr(bench_tasks, constant, None)
        assert isinstance(value, str) and "spec" in value, (
            f"{grader_type} points at {constant}, which is not an embedded grader source"
        )


def test_the_gate_is_reachable_from_the_shipped_runner() -> None:
    """Otherwise the early refusal guards a door nobody opens."""
    tree = ast.parse((REPO_ROOT / "minicc" / "benchmarks.py").read_text(encoding="utf-8"))
    hosts = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
             for inner in ast.walk(node)
             if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
             and inner.func.attr == "validate_task"}
    assert hosts, "benchmarks.py no longer calls validate_task, so the load-time door is dead"
    runner = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name in hosts)
    source = ast.unparse(runner)
    assert "v2_tasks" in source or "load_tasks" in source, (
        f"{runner.name} validates but never loads the suites it checks"
    )


def test_every_shipped_task_still_loads() -> None:
    """The new door must not reject the corpus it is supposed to protect."""
    offenders: list[str] = []
    for task in bench_tasks.v2_tasks():
        try:
            bench_tasks.validate_task(task)
        except ValueError as exc:
            offenders.append(f"{task.get('id')}: {exc}")
    legacy = load_tasks(REPO_ROOT / "benchmarks" / "tasks.json")
    assert len(legacy) >= 20, f"only {len(legacy)} legacy tasks read - the census saw nothing"
    assert offenders == [], f"shipped tasks now fail their own validator: {offenders}"
