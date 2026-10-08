"""M8-T107: a workspace the host could not write is NO-RESULT, not the agent's failure.

``run_benchmark`` prepared the fixture and ran the agent inside one ``try``, and
that block's ``except Exception`` booked ``status="failed"``. The grading block
below it then wrote ``passed=False`` plus a ``grader_type``, so every exception
out of ``prepare_fixture`` arrived as a verdict on work the agent never got the
chance to attempt.

Measured on ``e88aa4e`` with the fixture write forced to raise ``OSError``
(``tests/_probe107`` arrangement, plain ``run_benchmark`` call):

* the row carried ``passed=False``, ``grader_type="file_contract"`` and
  ``error="OSError: [Errno 28] No space left on device"``;
* ``build_report`` counted it in ``gradable_task_count``, so ``pass_at_1`` fell
  to ``0.0`` for a task nobody ran;
* because the diagnostic oracle re-ran the contract grader against the empty
  directory, a task whose contract an empty workspace satisfies also produced
  ``reviewer_false_negative_count=1`` - a signal about a reviewer that never
  reviewed anything.

The channel for "nobody judged this workspace" already existed (M8-T80 wrote it,
M8-T81 gave it a reader, M8-T83 and M8-T88 moved the other entrances onto it) and
the fixture stage was the one entrance still outside it. The gates below assert
the row, the whole shipped population of fixture tasks, the report, and - as the
control - that an agent which really failed still books ``passed=False``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

import minicc.benchmarks as benchmarks
from minicc.behavior_bench import behavior_tasks
from minicc.bench_tasks import v2_tasks
from minicc.benchmarks import build_report, markdown_report, run_benchmark

REPO_ROOT = Path(__file__).resolve().parent.parent

HOST_FAILURES = [
    pytest.param(OSError(28, "No space left on device"), id="oserror"),
    pytest.param(subprocess.TimeoutExpired(cmd="git init", timeout=60), id="git-timeout"),
]

#: The population floor: without one, a census over an empty task list passes.
MINIMUM_FIXTURE_TASKS = 30


def _task() -> dict[str, Any]:
    return {
        "id": "unwritable-workspace",
        "category": "write",
        "prompt": "把 a.py 里的 f 补全。",
        "fixture": {"a.py": "def f():\n    return 1\n"},
        "grader": {"type": "file_contract", "files": [{"path": "a.py", "exists": True}]},
    }


def _patch_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """A service that answers with a fixed completion, so no model is contacted."""
    from tests.test_benchmark_runner import _fake_provider_factory, _service_config

    _fake_provider_factory(monkeypatch)
    monkeypatch.setattr("minicc.config.load_config", _service_config)
    from minicc.web import AgentService

    original_init = AgentService.__init__

    def patched_init(self: Any, workspace: Any, config: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, workspace, _service_config(), *args, **kwargs)

    monkeypatch.setattr("minicc.web.AgentService.__init__", patched_init)


def _host_cannot_write(monkeypatch: pytest.MonkeyPatch, failure: BaseException) -> None:
    """Keyed on the patch target, not on a call argument: the runner calls this
    once per fixture task, and nothing else in the run may raise it."""

    def refuse(*args: object, **kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(benchmarks, "prepare_fixture", refuse)


# --- the row ---------------------------------------------------------------


@pytest.mark.parametrize("failure", HOST_FAILURES)
def test_a_workspace_the_host_could_not_write_is_no_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: BaseException
) -> None:
    _patch_service(monkeypatch)
    _host_cannot_write(monkeypatch, failure)

    row = run_benchmark([_task()], workspace=tmp_path)[0]

    assert row["passed"] is None, (
        f"a workspace the host never wrote was graded as the agent's failure: {row}"
    )
    assert row["grading_refused"] is True, row
    assert type(failure).__name__ in row["refusal"], row
    assert row["grader_type"] == "file_contract", row
    assert row["status"] == "failed", row
    # `error` is the agent's own diagnostic; there was no agent.
    assert not row.get("error"), row


@pytest.mark.parametrize("failure", HOST_FAILURES)
def test_the_diagnostic_oracle_does_not_judge_a_workspace_that_was_never_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: BaseException
) -> None:
    """The oracle re-runs the grader as a diagnostic on the row's workspace.

    On an unwritten workspace a contract an empty directory satisfies passes, and
    that pass used to be counted as a reviewer false negative (measured above).
    """
    _patch_service(monkeypatch)
    _host_cannot_write(monkeypatch, failure)
    vacuous = _task() | {"id": "unwritable-vacuous",
                         "grader": {"type": "file_contract",
                                    "files": [{"path": "gone.txt", "exists": False}]}}

    row = run_benchmark([vacuous], workspace=tmp_path)[0]

    assert row["passed"] is None, row
    assert row.get("objective_oracle") is None, (
        f"a grader that looked at an empty directory produced a signal about the agent: {row}"
    )


def test_a_fixture_task_graded_by_a_verify_command_also_refuses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The third place a row can be booked without a workspace.

    A legacy-shaped task (``verify_command``, no ``grader``) that also carries a
    fixture reaches the runner's last ``passed=False`` branch. No shipped task has
    that shape today; the branch is kept for one because a task file is data, and a
    rule nobody can reach is a rule nobody has witnessed.
    """
    _patch_service(monkeypatch)
    _host_cannot_write(monkeypatch, OSError(28, "No space left on device"))
    task = {"id": "unwritable-verify", "category": "write", "prompt": "改 LICENSE",
            "fixture": {"LICENSE": "MIT\n"}, "verify_command": "python -c pass"}

    row = run_benchmark([task], workspace=tmp_path)[0]

    assert row["passed"] is None, row
    assert row["grading_refused"] is True, row
    assert row["grader_type"] == "command", row


# --- the population --------------------------------------------------------


@pytest.mark.parametrize("failure", HOST_FAILURES)
def test_every_shipped_fixture_task_refuses_when_the_host_cannot_write_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: BaseException
) -> None:
    """One run over the shipped population, not one hand-built task.

    The behaviour gate above uses a task this file wrote; this one is the census
    that a real task set cannot reach a verdict through the fixture stage.
    """
    fixture_tasks = [task for task in behavior_tasks() + v2_tasks() if task.get("fixture")]
    assert len(fixture_tasks) >= MINIMUM_FIXTURE_TASKS, (
        f"the census is reading {len(fixture_tasks)} fixture tasks, below its floor"
    )
    by_id = {task["id"]: task for task in fixture_tasks}
    assert len(by_id) == len(fixture_tasks), "two shipped tasks share an id"

    _patch_service(monkeypatch)
    _host_cannot_write(monkeypatch, failure)
    rows = run_benchmark(fixture_tasks, workspace=tmp_path)

    assert {row["task_id"] for row in rows} == set(by_id), "the run did not cover the population"
    graded = [(row["task_id"], row["passed"]) for row in rows if row["passed"] is not None]
    assert graded == [], f"an unwritten workspace was graded: {graded}"
    for row in rows:
        assert row["grading_refused"] is True, row
        assert row["grader_type"] == by_id[row["task_id"]]["grader"]["type"], row


# --- the report ------------------------------------------------------------


def test_the_refusal_reaches_the_report_and_leaves_the_denominator_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_service(monkeypatch)
    _host_cannot_write(monkeypatch, OSError(28, "No space left on device"))
    task = _task()

    report = build_report([task], run_benchmark([task], workspace=tmp_path))
    metrics = report["metrics"]

    assert metrics["grading_refusal_count"] == 1, metrics
    assert metrics["gradable_task_count"] == 0, metrics
    assert metrics["pass_at_1"] is None, (
        f"a task nobody ran dilutes the pass rate: {metrics}"
    )
    assert metrics["reviewer_false_negative_count"] == 0, metrics
    markdown = markdown_report(report)
    assert "REFUSED" in markdown and "No space left on device" in markdown, markdown


def test_the_column_names_one_grader_in_the_runner_and_in_the_report() -> None:
    """The refusal and the report's own default must be the same rule.

    ``build_report`` rebuilds the row and has to name a grader for a row whose
    producer wrote none; if that default and the runner's refusal disagree, the
    same task has two answers to "who was supposed to look at this".

    Since M8-T139: a task that never ran has no grader_type in the report
    (the runner's refusal still knows the declared grader, but the report
    honestly says "nobody judged this").
    """
    task = _task()
    rebuilt = build_report([task], [])["results"][0]["grader_type"]
    assert rebuilt is None, f"not_run task must have no grader_type in the report, got {rebuilt!r}"
    legacy = {"id": "legacy", "category": "verify", "prompt": "回答任意内容。",
              "verify_command": "python -c pass"}
    assert build_report([legacy], [])["results"][0]["grader_type"] is None
    bare = {"id": "bare", "category": "chat", "prompt": "回答任意内容。"}
    assert build_report([bare], [])["results"][0]["grader_type"] is None


# --- control: the channel must not become a way to erase red ---------------


class _FailingService:
    """The agent's own run raises - a different stage from the host's write."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def _chat_locked(self, payload: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("provider exploded")

    def shutdown(self) -> None:
        pass


def test_an_agent_that_really_failed_still_books_a_verdict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from tests.test_benchmark_runner import _service_config

    monkeypatch.setattr("minicc.config.load_config", _service_config)
    monkeypatch.setattr("minicc.web.AgentService", _FailingService)

    row = run_benchmark([_task()], workspace=tmp_path)[0]

    assert row["status"] == "failed", row
    assert row["passed"] is False, row
    assert not row.get("grading_refused"), f"a real failure was laundered into a refusal: {row}"
    assert "RuntimeError" in str(row["error"]), row


def test_a_prepared_workspace_really_gets_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Reverse control for the gates above: the fixture stage must still run.

    They patch ``benchmarks.prepare_fixture``; if the runner stopped calling it,
    every assertion above would hold for the wrong reason and this one would go
    red on the missing file.
    """
    from tests.test_benchmark_runner import _service_config

    monkeypatch.setattr("minicc.config.load_config", _service_config)
    monkeypatch.setattr("minicc.web.AgentService", _FailingService)
    seen: dict[str, str] = {}
    real = benchmarks.prepare_fixture

    def record(task: dict[str, Any], workspace: Path, **kwargs: Any) -> None:
        real(task, workspace, **kwargs)
        seen["written"] = (workspace / "a.py").read_text(encoding="utf-8")

    monkeypatch.setattr(benchmarks, "prepare_fixture", record)

    run_benchmark([_task()], workspace=tmp_path)

    assert seen.get("written") == "def f():\n    return 1\n", seen
