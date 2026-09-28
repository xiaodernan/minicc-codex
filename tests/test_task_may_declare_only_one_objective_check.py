"""M8-T98: a task may declare one objective check, not two that shadow each other.

Measured on ``9e4a8d6``: ``load_tasks`` checked only ids, so a task carrying both a
``grader`` and a ``verify_command`` loaded happily - and in ``run_benchmark`` the grader
branch comes first, so the ``verify_command`` was never executed and the row said
"ungraded" with no word about the check that was dropped. The shipped legacy file has no
such conflict today (30 tasks, all ``verify_command``, none with a grader); this door keeps
it that way and refuses the combination instead of scoring less than the author wrote.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from minicc.benchmarks import load_tasks

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS_AST = ast.parse((REPO_ROOT / "minicc" / "benchmarks.py").read_text(encoding="utf-8"))
BASE = {"id": "task-shadowing-check", "category": "edit", "prompt": "p",
        "fixture": {"a.txt": "x"}}


def _load(tmp_path: Path, task: dict) -> list[dict]:
    fixture_file = tmp_path / "tasks.json"
    fixture_file.write_text(json.dumps([task]), encoding="utf-8")
    return load_tasks(fixture_file)


@pytest.mark.parametrize("grader_type", ["magic_oracle", "file_contract"])
def test_two_objective_checks_in_one_task_are_refused_naming_both(
    tmp_path: Path, grader_type: str
) -> None:
    task = {**BASE, "grader": {"type": grader_type, "files": []},
            "verify_command": "python -c \"print('never runs')\""}
    with pytest.raises(ValueError) as exc:
        _load(tmp_path, task)
    message = str(exc.value)
    assert BASE["id"] in message, message
    assert "verify_command" in message and grader_type in message, message


@pytest.mark.parametrize("spec_key", ["grader", "verify_command"])
def test_one_objective_check_still_loads(tmp_path: Path, spec_key: str) -> None:
    extra = ({spec_key: {"type": "file_contract", "files": [{"path": "a.txt"}]}}
             if spec_key == "grader" else {spec_key: "python -c \"print(1)\""})
    loaded = _load(tmp_path, {**BASE, **extra})
    assert loaded[0]["id"] == BASE["id"]


def test_the_runner_really_does_drop_the_second_check() -> None:
    """The refusal is justified by the dispatch order, read out of the source.

    If someone ever makes both checks run, this witness has to be updated - that is the
    point of keeping it, not a quirk of today's code.
    """
    runner = next(n for n in ast.walk(BENCHMARKS_AST)
                  if isinstance(n, ast.FunctionDef) and n.name == "run_benchmark")
    for node in ast.walk(runner):
        if not isinstance(node, ast.If):
            continue
        tested = ast.unparse(node.test)
        # ast.unparse quotes attribute names with single quotes, so matching on a
        # double-quoted spelling made this witness look for something that never appears.
        if "get('grader')" in tested and node.orelse:
            else_src = ast.unparse(node.orelse)
            assert 'verify_command' in else_src, (
                "the grader branch no longer shadows verify_command; re-check the loader rule"
            )
            return
    raise AssertionError("run_benchmark no longer branches on task['grader'] at all")


def test_the_shipped_legacy_suite_has_no_shadowing_task() -> None:
    raw = json.loads((REPO_ROOT / "benchmarks" / "tasks.json").read_text(encoding="utf-8"))
    assert len(raw) >= 20, f"only {len(raw)} legacy tasks read - the census saw nothing"
    conflicts = [t["id"] for t in raw if t.get("grader") and t.get("verify_command")]
    assert conflicts == [], f"shipped legacy tasks shadow a check: {conflicts}"
    # measured, not assumed: 3 of 30 legacy tasks carry a verify_command and the other 27
    # are prompt-only, so there is no objective check to shadow - the invariant is that no
    # single task declares both, not that every legacy task has a verify_command.
    with_check = sum(1 for t in raw if t.get("verify_command"))
    assert 0 < with_check < len(raw), f"legacy shape moved: {with_check}/{len(raw)}"
    assert len(load_tasks(REPO_ROOT / "benchmarks" / "tasks.json")) == len(raw)


def test_the_door_sits_on_the_suite_that_needs_it() -> None:
    """load_tasks is what the default (legacy) suite actually reads."""
    main = next(n for n in ast.walk(BENCHMARKS_AST)
                if isinstance(n, ast.FunctionDef) and n.name == "main")
    called = {ast.unparse(node.func) for node in ast.walk(main) if isinstance(node, ast.Call)}
    assert "load_tasks" in called, sorted(called)
    assert "validate_task" in called or "validate_behavior_task" in called, (
        "the other suites lost their own load-time doors"
    )
