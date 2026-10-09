"""M8-T113: an interrupted task is not a verdict either - the operator's Ctrl+C.

``run_benchmark`` records "nobody judged this workspace" as NO-RESULT
(``passed=None`` + ``grading_refused``) and the grading block honours it, but
only for the doors that already carried the mark. The BaseException door - the
one an operator opens with Ctrl+C - wrote ``status="interrupted"`` plus a
recorded reason and then fell through to the same ``passed=None`` (NO-RESULT) as
an agent that really failed, and to the same diagnostic oracle.

Measured on ``9a9d55a`` (``_probe111.py``, plain ``run_benchmark`` call, a
contract an empty directory satisfies so the diagnostic is legible as a number):

* the row carried ``passed=None``, ``grader_type="file_contract"``,
  ``error="KeyboardInterrupt"`` and ``objective_oracle={"passed": True,
  "case_count": 1}``, whether the interrupt landed in ``prepare_fixture`` or in
  the agent phase;
* ``build_report`` did NOT count it in ``gradable_task_count``, so ``pass_at_1``
  stayed correct for a task no run ever finished;
* ``reviewer_false_negative_count`` read ``0`` - no reviewer was asked.

The gates below assert the row, the oracle, the third door (a legacy task graded
by ``verify_command``), the whole shipped legacy population, and the report. The
control lives beside them: a completed row in the same run keeps its verdict, so
the refusal channel cannot become a way to erase a real pass.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import minicc.bench_tasks as bench_tasks
import minicc.benchmarks as benchmarks
from minicc.benchmarks import build_report, load_tasks, markdown_report, run_benchmark

#: Every task in this file is judged by a contract that an *empty* workspace
#: satisfies, so an oracle that runs at all is visible as a passing one. A
#: contract that failed everywhere would hide the defect behind the number it
#: reports.
CONTRACT_AN_EMPTY_WORKSPACE_SATISFIES = {
    "type": "file_contract", "files": [{"path": "gone.txt", "exists": False}],
}

#: The census floor: without one, a suite that stopped shipping tasks passes.
MINIMUM_LEGACY_TASKS = 30


def _task(task_id: str) -> dict[str, Any]:
    return {
        "id": task_id,
        "category": "write",
        "prompt": "把 a.py 里的 f 补全。",
        "fixture": {"a.py": "def f():\n    return 1\n"},
        "grader": CONTRACT_AN_EMPTY_WORKSPACE_SATISFIES,
    }


class _InterruptingService:
    """The agent phase raises the operator's interrupt; no model is contacted."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def _chat_locked(self, payload: object, **kwargs: object) -> dict[str, object]:
        raise KeyboardInterrupt()

    def shutdown(self) -> None:
        pass


def _patch_service(monkeypatch: pytest.MonkeyPatch, service: type = _InterruptingService) -> None:
    from tests.test_benchmark_runner import _service_config

    monkeypatch.setattr("minicc.config.load_config", _service_config)
    monkeypatch.setattr("minicc.web.AgentService", service)


def _interrupt_the_fixture_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """The other stage the operator can interrupt: the host's own write."""
    def refuse(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt()

    monkeypatch.setattr(benchmarks, "prepare_fixture", refuse)


def _run_one(task: dict[str, Any], workspace: Path) -> dict[str, Any]:
    """Run one task to its interrupt and read the row off the results file.

    The row has to come from disk, not from the return value: an interrupted run
    never returns, and the durable row is the whole point of the record.
    """
    results_path = workspace.parent / f"results-{task['id']}.json"
    with pytest.raises(KeyboardInterrupt):
        run_benchmark([task], workspace=workspace, results_path=results_path)
    rows = json.loads(results_path.read_text(encoding="utf-8"))
    assert len(rows) == 1, rows
    return rows[0]


# --- the row ---------------------------------------------------------------


@pytest.mark.parametrize("door", ["agent", "prepare"])
def test_an_interrupted_task_is_refused_not_failed(
    door: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_service(monkeypatch)
    if door == "prepare":
        _interrupt_the_fixture_write(monkeypatch)
    task = _task(f"interrupted-in-{door}")

    row = _run_one(task, tmp_path / door)

    assert row["status"] == "interrupted", row
    assert row["passed"] is None, (
        f"an operator's Ctrl+C was booked as the agent's failure: {row}"
    )
    assert row["grading_refused"] is True, row
    assert "KeyboardInterrupt" in row["refusal"], row
    # Who *would* have judged it stays named, so the report can be read.
    assert row["grader_type"] == "file_contract", row
    # `error` is the agent's own diagnostic; an interrupt is the operator's.
    assert not row.get("error"), row


@pytest.mark.parametrize("door", ["agent", "prepare"])
def test_the_diagnostic_oracle_does_not_run_during_an_interrupt(
    door: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The oracle re-runs the grader as a diagnostic on the row's workspace.

    Measured above: during an abort it re-judged the workspace and reported
    ``passed=True`` on this contract, which is a reviewer false negative about a
    reviewer nobody asked.
    """
    _patch_service(monkeypatch)
    if door == "prepare":
        _interrupt_the_fixture_write(monkeypatch)

    row = _run_one(_task(f"oracle-in-{door}"), tmp_path / door)

    assert row["passed"] is None, row
    assert row.get("objective_oracle") is None, (
        f"a grader ran during an abort and produced a signal about the agent: {row}"
    )


def test_an_interrupted_legacy_task_graded_by_a_verify_command_also_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The third door: no fixture, no grader, a ``verify_command`` instead.

    This is the shape the shipped legacy suite uses, so the refusal has to name
    ``command`` there rather than reaching for a grader the task never declared.
    """
    _patch_service(monkeypatch)
    task = {"id": "legacy-interrupted", "category": "verify", "prompt": "回答任意内容。",
            "verify_command": "python -c pass"}

    row = _run_one(task, tmp_path)

    assert row["passed"] is None, row
    assert row["grading_refused"] is True, row
    assert row["grader_type"] == "command", row
    assert "KeyboardInterrupt" in row["refusal"], row


# --- the population --------------------------------------------------------


def test_every_shipped_legacy_task_refuses_when_the_run_is_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One run per shipped task, not one hand-built task.

    The gate above uses a task this file wrote; this is the census that the
    suite people actually run cannot reach a verdict through the interrupt. An
    interrupted run aborts at the first task, so the census reads one row per
    run rather than one run over the population.
    """
    tasks = load_tasks()
    assert len(tasks) >= MINIMUM_LEGACY_TASKS, (
        f"the census is reading {len(tasks)} shipped tasks, below its floor"
    )
    _patch_service(monkeypatch)

    graded: list[tuple[str, object]] = []
    for index, task in enumerate(tasks):
        row = _run_one(task, tmp_path / f"ws{index}")
        if row["passed"] is not None:
            graded.append((row["task_id"], row["passed"]))
        assert row["grading_refused"] is True, row
        assert "KeyboardInterrupt" in row["refusal"], row

    assert graded == [], f"an interrupted task was graded: {graded}"


# --- the report ------------------------------------------------------------


def test_the_interrupt_reaches_the_report_and_leaves_the_denominator_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_service(monkeypatch)
    task = _task("interrupted-report")

    report = build_report([task], [_run_one(task, tmp_path)])
    metrics = report["metrics"]

    assert metrics["grading_refusal_count"] == 1, metrics
    assert metrics["gradable_task_count"] == 0, metrics
    assert metrics["pass_at_1"] is None, (
        f"an interrupted task diluted the pass rate: {metrics}"
    )
    assert metrics["reviewer_false_negative_count"] == 0, metrics
    markdown = markdown_report(report)
    assert "REFUSED" in markdown and "KeyboardInterrupt" in markdown, markdown
    # The row's own status still says how the run ended.
    assert "| interrupted |" in markdown, markdown


# --- control: the channel must not become a way to erase a real verdict ----


class _OneCompletedThenInterrupted:
    """Answers the first task, then the operator interrupts the second."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def _chat_locked(self, payload: dict[str, Any], **kwargs: object) -> dict[str, Any]:
        if payload["message"] == "interrupt me":
            raise KeyboardInterrupt()
        return {"answer": "done", "completion": {"status": "complete"}}

    def shutdown(self) -> None:
        pass


def test_a_completed_row_beside_the_interrupt_keeps_its_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_service(monkeypatch, _OneCompletedThenInterrupted)
    done = _task("done")
    done["prompt"] = "done"
    stopped = _task("stopped")
    stopped["prompt"] = "interrupt me"
    results_path = tmp_path / "results.json"

    with pytest.raises(KeyboardInterrupt):
        run_benchmark([done, stopped], workspace=tmp_path, results_path=results_path)

    rows = {row["task_id"]: row for row in json.loads(results_path.read_text(encoding="utf-8"))}
    assert rows["done"]["passed"] is True, rows["done"]
    assert not rows["done"].get("grading_refused"), rows["done"]
    assert rows["stopped"]["passed"] is None, rows["stopped"]
    assert rows["stopped"]["grading_refused"] is True, rows["stopped"]


def test_the_interrupt_constructor_is_the_same_verdict_as_the_other_no_result_doors() -> None:
    """A third account, not a third shape: the shared keys must not drift."""
    interrupt = bench_tasks.run_interrupted("file_contract", KeyboardInterrupt())
    host = bench_tasks.workspace_unwritable("file_contract", OSError(28, "No space left on device"))
    grader = bench_tasks.grader_unable("file_contract", OSError("cannot start"))
    assert interrupt["passed"] is host["passed"] is grader["passed"] is None
    assert interrupt["grading_refused"] is host["grading_refused"] is grader["grading_refused"] is True
    assert set(interrupt) == set(host) == set(grader)
    assert interrupt["refusal"] == "KeyboardInterrupt", interrupt
    assert "OSError" in host["refusal"] and "OSError" in grader["refusal"]
