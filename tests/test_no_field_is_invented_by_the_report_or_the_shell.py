"""M8-T100: refuse fields the report or the shell would otherwise invent.

Measured on ``8d7cc8f``: every legacy task already carries a non-blank ``category``, and 27
of 30 carry ``verify_command: null`` - falsy, so the runner skips that branch and my first
guess (any non-string command gets stringified) needed correcting. The reachable silences
are a missing or blank ``category`` becoming the report word ``uncategorized``, and a
truthy non-string ``verify_command`` reaching ``str(verify_command)`` in ``run_benchmark``:
a nonsense command line that fails and is booked on the agent.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import minicc.bench_tasks as bench_tasks
from minicc.benchmarks import load_tasks

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCH_SRC = (REPO_ROOT / "minicc" / "benchmarks.py").read_text(encoding="utf-8")
BASE = {"id": "shape-check-task", "prompt": "统计 a.txt 的行数。", "category": "verify",
        "verify_command": "python -c \"print(1)\""}


def _legacy(tmp_path: Path, task: dict) -> Path:
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps([task]), encoding="utf-8")
    return path


@pytest.mark.parametrize("category", [
    pytest.param(None, id="null"),
    pytest.param("", id="empty"),
    pytest.param("   ", id="whitespace"),
    pytest.param(7, id="not-a-string"),
])
def test_a_category_the_report_would_invent_is_refused(tmp_path: Path, category: object) -> None:
    task = {**BASE, "category": category}
    with pytest.raises(ValueError) as exc:
        load_tasks(_legacy(tmp_path, task))
    assert "category" in str(exc.value) and BASE["id"] in str(exc.value), exc.value


def test_a_task_without_any_category_is_refused_too(tmp_path: Path) -> None:
    task = {k: v for k, v in BASE.items() if k != "category"}
    with pytest.raises(ValueError) as exc:
        load_tasks(_legacy(tmp_path, task))
    assert "category" in str(exc.value), exc.value


@pytest.mark.parametrize("command", [
    pytest.param("", id="empty-string"),
    pytest.param("   ", id="whitespace-string"),
    pytest.param(["python", "-c", "print(1)"], id="list-would-be-stringified"),
    pytest.param({"cmd": "python"}, id="dict-would-be-stringified"),
])
def test_a_truthy_non_string_command_is_refused(tmp_path: Path, command: object) -> None:
    task = {**BASE, "verify_command": command}
    with pytest.raises(ValueError) as exc:
        load_tasks(_legacy(tmp_path, task))
    message = str(exc.value)
    assert "verify_command" in message and BASE["id"] in message, message


@pytest.mark.parametrize("command", [
    pytest.param(None, id="null-is-prompt-only"),
    pytest.param("python -c \"print(1)\"", id="real-command"),
])
def test_the_two_honest_shapes_still_load(tmp_path: Path, command: object) -> None:
    assert load_tasks(_legacy(tmp_path, BASE))[0]["id"] == BASE["id"]
    task = {**BASE, "verify_command": command}
    assert load_tasks(_legacy(tmp_path, task))[0]["id"] == BASE["id"]


def test_both_doors_ask_the_same_owner() -> None:
    tree = ast.parse(BENCH_SRC)
    loader = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "load_tasks")
    assert any(isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
               and c.func.attr == "require_objective_shape" for c in ast.walk(loader)), \
        "load_tasks no longer asks the shared owner"

    validator = next(n for n in ast.walk(ast.parse(
        (REPO_ROOT / "minicc" / "bench_tasks.py").read_text(encoding="utf-8")))
        if isinstance(n, ast.FunctionDef) and n.name == "validate_task")
    assert any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
               and c.func.id == "require_objective_shape" for c in ast.walk(validator)), \
        "validate_task no longer asks the shared owner"


def test_the_coercions_the_door_replaces_are_still_there() -> None:
    """If either disappears, this witness has to be re-thought rather than left true."""
    runner = next(n for n in ast.walk(ast.parse(BENCH_SRC))
                  if isinstance(n, ast.FunctionDef) and n.name == "run_benchmark")
    assert any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == "str"
               and isinstance(c.args[0], ast.Name) and c.args[0].id == "verify_command"
               for c in ast.walk(runner)), "run_benchmark no longer stringifies verify_command"
    report = next(n for n in ast.walk(ast.parse(BENCH_SRC))
                  if isinstance(n, ast.FunctionDef) and n.name == "build_report")
    assert "uncategorized" in ast.unparse(report), "build_report no longer invents a category"


def test_the_shipped_suites_satisfy_the_new_door() -> None:
    counts = {}
    for name in ("benchmarks/tasks.json", "benchmarks/tasks.v2.json"):
        raw = json.loads((REPO_ROOT / name).read_text(encoding="utf-8"))
        tasks = raw if isinstance(raw, list) else raw.get("tasks", [])
        assert len(tasks) >= 20, f"{name}: only {len(tasks)} tasks read - the census saw nothing"
        offenders = []
        for task in tasks:
            try:
                bench_tasks.require_objective_shape(task)
            except ValueError as exc:
                offenders.append(f"{task.get('id')}: {exc}")
        assert offenders == [], f"{name}: {offenders}"
        counts[name] = len(tasks)
    assert len(load_tasks(REPO_ROOT / "benchmarks" / "tasks.json")) == counts["benchmarks/tasks.json"]
