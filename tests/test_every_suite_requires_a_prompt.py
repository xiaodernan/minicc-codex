"""M8-T99: every suite's loader has to refuse a task that asks nothing.

Measured on ``d08b476``: ``run_benchmark`` builds the model message as
``str(current_task.get("prompt") or "")`` (``minicc/benchmarks.py:725``), so a blank or
missing prompt buys a full agent turn with nothing asked. ``validate_task`` refused that for
v2 - but the check was inline, so the legacy loader (``load_tasks``) had no share of it and
its own gate had never been asked.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import minicc.bench_tasks as bench_tasks
from minicc.benchmarks import load_tasks

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS_AST = ast.parse((REPO_ROOT / "minicc" / "benchmarks.py").read_text(encoding="utf-8"))
BASE = {"id": "quiet-task", "category": "edit"}

BAD_PROMPTS = [
    pytest.param({}, id="missing"),
    pytest.param({"prompt": ""}, id="empty"),
    pytest.param({"prompt": "   \n\t "}, id="whitespace"),
    pytest.param({"prompt": None}, id="null"),
    pytest.param({"prompt": 12}, id="not-a-string"),
]


def _legacy_file(tmp_path: Path, task: dict) -> Path:
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps([task]), encoding="utf-8")
    return path


@pytest.mark.parametrize("extra", BAD_PROMPTS)
def test_the_legacy_loader_refuses_a_task_that_asks_nothing(tmp_path: Path, extra: dict) -> None:
    task = {**BASE, **extra, "verify_command": "python -c \"print(1)\""}
    with pytest.raises(ValueError) as exc:
        load_tasks(_legacy_file(tmp_path, task))
    message = str(exc.value)
    assert "prompt 不能为空" in message, message
    assert BASE["id"] in message, (
        "a refusal that does not name the task id cannot be acted on in a 30-task file"
    )


@pytest.mark.parametrize("extra", BAD_PROMPTS)
def test_the_v2_door_refuses_the_same_shapes_through_the_same_owner(extra: dict) -> None:
    task = {"id": "quiet-task", "category": "edit", "max_minutes": 5,
            "fixture": {"a.txt": "x"}, "grader": {"type": "file_contract",
                                                  "files": [{"path": "a.txt"}]}, **extra}
    with pytest.raises(ValueError) as exc:
        bench_tasks.validate_task(task)
    # v2 lists prompt as a required key, so the missing case is refused one check earlier;
    # both messages name prompt, and the structural gate below proves the shared owner is
    # the one that speaks for the shapes that reach it.
    assert "prompt" in str(exc.value), exc.value


def test_a_task_that_asks_something_still_loads(tmp_path: Path) -> None:
    task = {**BASE, "prompt": "统计 a.txt 的行数。", "verify_command": "python -c \"print(1)\""}
    assert load_tasks(_legacy_file(tmp_path, task))[0]["id"] == BASE["id"]


def test_there_is_one_owner_of_the_rule_and_both_doors_use_it() -> None:
    """Otherwise the rule quietly grows a second copy in whichever loader is edited later."""
    main = next(n for n in ast.walk(BENCHMARKS_AST)
                if isinstance(n, ast.FunctionDef) and n.name == "load_tasks")
    assert any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
               and node.func.attr == "require_prompt" for node in ast.walk(main)), \
        "load_tasks no longer asks the shared owner"

    validator = next(n for n in ast.walk(ast.parse(
        (REPO_ROOT / "minicc" / "bench_tasks.py").read_text(encoding="utf-8")))
        if isinstance(n, ast.FunctionDef) and n.name == "validate_task")
    assert any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
               and node.func.id == "require_prompt" for node in ast.walk(validator)), \
        "validate_task no longer asks the shared owner"

    owner = next(n for n in ast.walk(ast.parse(
        (REPO_ROOT / "minicc" / "bench_tasks.py").read_text(encoding="utf-8")))
        if isinstance(n, ast.FunctionDef) and n.name == "require_prompt")
    assert len([node for node in ast.walk(owner)
                if isinstance(node, ast.Constant) and node.value == "prompt"]) >= 1
    inline = [n for n in ast.walk(validator)
              if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name)
              and n.value.id == "task" and isinstance(n.slice, ast.Constant)
              and n.slice.value == "prompt"]
    assert not inline, "validate_task re-reads task['prompt'] itself; the rule has two owners"


def test_the_runner_still_buys_a_run_for_an_empty_message() -> None:
    """Why the door is needed: the read that would turn "no prompt" into a paid turn."""
    runner = next(n for n in ast.walk(BENCHMARKS_AST)
                  if isinstance(n, ast.FunctionDef) and n.name == "run_benchmark")
    reads = [node for node in ast.walk(runner) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and node.func.attr == "get"
             and node.args and isinstance(node.args[0], ast.Constant)
             and node.args[0].value == "prompt"]
    assert reads, (
        "run_benchmark no longer reads the prompt defensively; re-check whether this door "
        "is still the guard it claims to be, then update this witness"
    )


def test_both_shipped_suites_ask_something() -> None:
    """The door must not reject the data it protects - measured, not assumed."""
    counts = {}
    for name in ("benchmarks/tasks.json", "benchmarks/tasks.v2.json",
                 "benchmarks/behavior-tasks.json"):
        raw = json.loads((REPO_ROOT / name).read_text(encoding="utf-8"))
        tasks = raw if isinstance(raw, list) else raw.get("tasks", [])
        assert len(tasks) >= 10, f"{name}: only {len(tasks)} tasks read - the census saw nothing"
        silent = [t.get("id") for t in tasks if not str(t.get("prompt") or "").strip()]
        assert silent == [], f"{name} has tasks that ask nothing: {silent}"
        counts[name] = len(tasks)
    assert len(load_tasks(REPO_ROOT / "benchmarks" / "tasks.json")) == counts["benchmarks/tasks.json"]
