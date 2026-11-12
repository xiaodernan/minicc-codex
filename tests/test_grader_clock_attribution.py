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


def test_a_workspace_that_never_returns_is_a_failure_not_a_no_result(tmp_path: Path) -> None:
    """The real thing: a fixture that loops forever, graded through a real child."""
    task = behavior_tasks()[0]
    prepare_fixture(task, tmp_path)
    (tmp_path / "solution.py").write_text(_hanging_source(task), encoding="utf-8")
    graded = grade_behavior(task, tmp_path, timeout=5)
    assert graded["passed"] is False, graded
    assert graded["agent_code_timed_out"] is True, graded
    assert "error" not in graded, graded
    assert graded["case_count"] == len(task["grader"]["cases"]) + len(task["grader"].get("raises", [])), graded


@pytest.mark.parametrize("child_output,verdict", [
    ("", "no-result"),
    ("MINICC_BEHAVIOR_PROGRESS:import\n", "verdict"),
    ("MINICC_BEHAVIOR_PROGRESS:call:0\n", "verdict"),
])
def test_the_partial_output_of_the_killed_child_decides_attribution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, child_output: str, verdict: str
) -> None:
    """Reverse control: one exception, three child outputs, two verdicts.

    A real run cannot produce the empty-output arm on demand - that is the whole
    point of the marker - so the wall clock is replaced and only the evidence the
    host would have read is varied.
    """

    def timed_out(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd="grader", timeout=20, output=child_output)

    monkeypatch.setattr("minicc.behavior_bench.subprocess.run", timed_out)
    graded = grade_behavior({"grader": {"type": "python_behavior", "function": "f", "cases": []}}, tmp_path)
    if verdict == "no-result":
        assert graded["passed"] is None, graded
        assert graded["grading_refused"] is True, graded
        assert "TimeoutExpired" in graded["refusal"], graded
        assert "agent_code_timed_out" not in graded, graded
    else:
        assert graded["passed"] is False, graded
        assert graded["agent_code_timed_out"] is True, graded
        assert "grading_refused" not in graded, graded


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


def test_a_verify_command_that_burned_its_budget_is_still_a_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The command did start and ran 300s inside the workspace: keep the verdict.

    The host cannot see inside a task own command, so this entrance keeps the
    coarser half of the rule and must not drift into the refusal channel that the
    other half now uses.
    """
    real_run = subprocess.run
    task, row = _run_verify_command(
        monkeypatch, tmp_path,
        _only_for_the_verify_command(real_run, subprocess.TimeoutExpired(cmd="echo verify", timeout=300)))
    assert row["passed"] is False, row
    assert "grading_refused" not in row, row
    assert row["grader_type"] == "command", row
    metrics = benchmarks.build_report([task], [row])["metrics"]
    assert metrics["grading_refusal_count"] == 0, metrics
    assert metrics["pass_at_1"] == 0.0, metrics


# --- structural controls ------------------------------------------------------


def _call_positions(node: ast.AST, target: str) -> list[tuple[int, int]]:
    return sorted(
        (sub.lineno, sub.col_offset)
        for sub in ast.walk(node)
        if isinstance(sub, ast.Call) and ast.unparse(sub.func) == target
    )


def test_the_grader_marks_progress_before_every_call_into_the_workspace() -> None:
    """Move a marker after the call it precedes and this gate is red."""
    tree = ast.parse(behavior_bench._GRADER)
    loops = [node for node in ast.walk(tree) if isinstance(node, ast.For)]
    assert len(loops) == 2, "the cases/raises loops moved; this gate is reading the wrong tree"
    for loop in loops:
        marks, calls = _call_positions(loop, "progress"), _call_positions(loop, "function")
        assert marks and calls, ast.unparse(loop)[:200]
        assert min(marks) < min(calls), "the marker no longer precedes the call into the workspace"
    loaded = _call_positions(tree, "spec.loader.exec_module")
    assert loaded and min(_call_positions(tree, "progress")) < min(loaded), (
        "no marker before the module load, so a hang during import would read as a host failure")


def test_the_prefix_the_host_reads_is_the_prefix_the_grader_writes() -> None:
    assert behavior_bench._BEHAVIOR_PROGRESS_PREFIX in behavior_bench._GRADER, \
        "the two halves of the handshake drifted apart"


def _written_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Dict):
        return [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
    if isinstance(node, ast.Call):
        return [k.arg for k in node.keywords if k.arg]
    return []


def test_the_behavior_grader_never_writes_the_key_that_shadowed_the_agent_error(
) -> None:
    """``error`` held the exception name and the agent own error string at once."""
    tree = ast.parse(Path(behavior_bench.__file__).read_text(encoding="utf-8"))
    written = {name for node in ast.walk(tree) for name in _written_names(node)}
    assert "error" not in written, "the field that shadowed the agent error came back"
    assert {"case_count", "agent_code_timed_out"} <= written, \
        "the census is not reading the returned rows at all"


def test_the_shadowing_census_can_see_a_planted_write() -> None:
    """Reverse control for the census above."""
    planted = ast.parse("def f():\n    return {'passed': False, 'error': 'boom'}\n")
    written = {name for node in ast.walk(planted) for name in _written_names(node)}
    assert "error" in written
