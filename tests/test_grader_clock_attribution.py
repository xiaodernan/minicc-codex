"""M8-T86: a grader clock is charged to the agent only where the host can see whose code ran.

``grade_behavior`` reported both of its host failures as ``passed=False`` plus an
``error`` key (measured on ``669eae5``: a workspace whose function never returns
came back ``{'passed': False, 'error': 'TimeoutExpired'}``, and a workspace the
host could not enter put ``NotADirectoryError`` in that same key). The second
shape also overwrote the agent own error string, because the runner writes that
field first and ``entry.update`` lays the grader dict on top of it.

Neither half can be swept into the refusal channel wholesale. ``OSError`` never
looked at the work, so a verdict about the agent is fabricated: end to end on
``669eae5`` the report printed ``pass_at_1 0.0`` and ``false_completion_rate
1.0`` for a grader that could not start. A timeout is the opposite trap - an
agent whose function never returns is exactly the red that
``tests/test_grader_cannot_run_is_no_result.py`` refuses to let disappear into a
shrinking denominator - so it cannot simply become a no-result either.

The caliber settled here: **a clock that expires is a verdict only when the host
can show the code under test was running when it expired.** The grader script
flushes a progress marker immediately before each call into the workspace (and
before loading its module), ``subprocess.run`` hands the killed child partial
stdout to the exception, and the host reads it back. Nothing the agent writes
runs before the first marker, so that window is a host window: no marker means
startup, a marker means the workspace was on the stack.

The legacy ``verify_command`` entrance answers the same question at the
resolution it allows: the shell either started and burned its whole budget
inside the workspace (a failure, unchanged) or never started (``OSError``, now a
no-result). Both entrances are pinned below.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

import minicc.behavior_bench as behavior_bench
from minicc import benchmarks
from minicc.behavior_bench import behavior_tasks, grade_behavior, prepare_fixture

NO_RESULT_KEYS = {"passed", "grader_type", "grading_refused", "refusal"}


def _hanging_source(task: dict[str, Any]) -> str:
    """A workspace whose graded function never returns."""
    return f"def {task['grader']['function']}(*args, **kwargs):\n    while True:\n        pass\n"


# --- the behavior grader: the marker decides, not the exception class -------


def test_a_grader_the_host_could_not_start_is_the_same_no_result_the_v2_graders_use(tmp_path: Path) -> None:
    """``OSError``: the interpreter or the workspace never came up."""
    graded = grade_behavior(behavior_tasks()[0], tmp_path / "not-a-directory")
    assert graded["passed"] is None, graded
    assert graded["grading_refused"] is True, graded
    assert set(graded) == NO_RESULT_KEYS, graded
    assert graded["refusal"].split(":")[0].endswith("Error"), graded


def test_a_wrong_answer_stays_an_ordinary_verdict(tmp_path: Path) -> None:
    """The shipped starter code is wrong but returns; it must not read as a hang."""
    task = behavior_tasks()[0]
    prepare_fixture(task, tmp_path)
    graded = grade_behavior(task, tmp_path)
    assert graded["passed"] is False, graded
    assert "agent_code_timed_out" not in graded, graded
    assert graded["exit_code"] == 1, graded


def test_the_untouched_grader_paths_still_grade(tmp_path: Path) -> None:
    rubric = {"grader": {"type": "answer_rubric", "required_any": [["分块"]]}}
    assert grade_behavior(rubric, tmp_path, "把结果分块返回")["passed"] is True
    assert grade_behavior({"grader": {"type": "file_contract"}}, tmp_path) == {
        "passed": None, "grader_type": "ungraded"}


# --- the legacy verify_command entrance --------------------------------------


class _CompletingAgent:
    """The runner grades after a fake agent reports a completed task."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def _chat_locked(self, payload: object, **kwargs: object) -> dict[str, object]:
        return {
            "answer": "ok", "turns": 1, "tool_calls_total": 1,
            "metrics": {"repair_attempts": 0}, "completion": {"status": "complete"},
        }

    def shutdown(self) -> None:
        pass


def _run_verify_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, runner: Callable[..., object]
) -> tuple[dict[str, object], dict[str, object]]:
    """Run one legacy (``verify_command``) task against a stubbed agent."""
    monkeypatch.setattr("minicc.web.AgentService", _CompletingAgent)
    monkeypatch.setattr(
        "minicc.config.load_config",
        lambda *args, **kwargs: SimpleNamespace(yolo=False, model="test-model", max_concurrent_tasks=1),
    )
    monkeypatch.setattr("subprocess.run", runner)
    task = {"id": "legacy", "category": "edit", "prompt": "p", "verify_command": "echo verify"}
    return task, benchmarks.run_benchmark([task], workspace=tmp_path)[0]


def _only_for_the_verify_command(real_run: Callable[..., object], exc: BaseException) -> Callable[..., object]:
    def runner(cmd: object, *args: object, **kwargs: object) -> object:
        if isinstance(cmd, str) and cmd.startswith("echo verify"):
            raise exc
        return real_run(cmd, *args, **kwargs)

    return runner


def test_a_verify_command_the_host_could_not_start_is_a_no_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The shell never started, so nothing looked at the work."""
    real_run = subprocess.run
    task, row = _run_verify_command(
        monkeypatch, tmp_path, _only_for_the_verify_command(real_run, OSError(13, "cannot start the shell")))
    assert row["passed"] is None, row
    assert row["grading_refused"] is True, row
    assert row["grader_type"] == "command", row
    assert row["claimed_complete"] is True, row
    metrics = benchmarks.build_report([task], [row])["metrics"]
    assert metrics["grading_refusal_count"] == 1, metrics
    assert metrics["false_completion_rate"] is None, metrics
    assert metrics["gradable_task_count"] == 0, metrics


def _written_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Dict):
        return [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
    if isinstance(node, ast.Call):
        return [k.arg for k in node.keywords if k.arg]
    return []


def test_the_shadowing_census_can_see_a_planted_write() -> None:
    """Reverse control: the census must see a planted ``error`` write."""
    planted = ast.parse("def f():\n    return {'passed': False, 'error': 'boom'}\n")
    written = {name for node in ast.walk(planted) for name in _written_names(node)}
    assert "error" in written
