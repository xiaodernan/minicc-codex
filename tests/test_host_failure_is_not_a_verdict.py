"""M8-T88: a verification command nobody ran is not the agent's failure either.

M8-T80 opened the NO-RESULT channel, M8-T81 gave the report a reader for it and
M8-T83 moved two grader entrances onto it (``tests/test_grader_cannot_run_is_no_result.py``).
Two entrances were still missing (measured on ``64a82f9``):

* ``run_benchmark``'s legacy ``verify_command`` branch caught ``TimeoutExpired``
  and ``OSError`` and wrote ``entry["passed"] = False``. This is not a
  hypothetical: 3 of the 30 tasks in ``benchmarks/tasks.json`` carry a
  ``verify_command`` and no ``grader``, so a host timeout on those three is
  currently booked as the agent claiming work it did not do.
* ``behavior_bench.grade_behavior`` caught the same pair and returned
  ``{"passed": False, ..., "error": ...}`` - the shape M8-T83 removed from the
  contract graders because ``error`` also shadowed the agent's own error string.

The gates below are paired with a census over every production module: an
exception handler that names a host failure must not emit a verdict, in any of
the three syntaxes code uses to write one.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

import minicc.bench_tasks as bench_tasks
import minicc.behavior_bench as behavior_bench
import minicc.benchmarks as benchmarks
from minicc.benchmarks import build_report, run_benchmark

REPO_ROOT = Path(__file__).resolve().parent.parent
NO_RESULT_KEYS = {"passed", "grader_type", "grading_refused", "refusal"}

HOST_FAILURES = [
    pytest.param(subprocess.TimeoutExpired(cmd="verify", timeout=1), id="timeout"),
    pytest.param(OSError(2, "No such file or directory"), id="oserror"),
]


# --- entrance 1: the runner's legacy verify_command branch --------------------


def _legacy_task(command: str) -> dict[str, object]:
    return {"id": "legacy-verify", "category": "verify", "prompt": "回答任意内容。",
            "verify_command": command}


def _drive_runner(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, command: str,
                  failure: BaseException | None) -> dict[str, object]:
    """Run one legacy task, raising ``failure`` only for its verify command.

    The patch is keyed on the command text on purpose: ``subprocess.run`` is
    process-global, and a blanket raise would break whatever the agent or the
    fixture happens to shell out to instead of measuring the grading branch.
    """
    from tests.test_benchmark_runner import _fake_provider_factory, _service_config

    _fake_provider_factory(monkeypatch)
    monkeypatch.setattr("minicc.config.load_config", _service_config)
    from minicc.web import AgentService

    original_init = AgentService.__init__

    def patched_init(self, workspace, config, *args, **kwargs):
        original_init(self, workspace, _service_config(), *args, **kwargs)

    monkeypatch.setattr("minicc.web.AgentService.__init__", patched_init)

    real_run = subprocess.run

    def selective_run(run_command, *args, **kwargs):
        if failure is not None and str(run_command) == command:
            raise failure
        return real_run(run_command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", selective_run)
    results = run_benchmark([_legacy_task(command)], workspace=tmp_path)
    return results[0]


@pytest.mark.parametrize("failure", HOST_FAILURES)
def test_a_verify_command_the_host_could_not_run_is_no_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: BaseException
) -> None:
    row = _drive_runner(monkeypatch, tmp_path, "python -c \"print('ok')\"", failure)
    assert row["passed"] is None, (
        f"a verification command that never reported a result was booked as the agent's failure: {row}"
    )
    assert row["grading_refused"] is True, row
    assert type(failure).__name__ in row["refusal"], row
    assert row["grader_type"] == "command", row


def test_a_verify_command_that_really_ran_is_still_a_verdict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Control for the gate above: the branch must not become a way to erase red.

    A command that reports a nonzero exit is the workspace's own failure, and it
    has to stay ``passed=False`` with no refusal attached.
    """
    row = _drive_runner(monkeypatch, tmp_path, "python -c \"raise SystemExit(3)\"", None)
    assert row["passed"] is False, row
    assert not row.get("grading_refused"), row
    assert row["grader_type"] == "command", (
        f"the verdict path must own its grader_type, or the field has two masters: {row}"
    )


def test_the_legacy_refusal_keeps_the_agent_own_error_field(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """M8-T83 measured that a grader ``error`` key replaced the agent's diagnosis.

    The refusal has to arrive in ``refusal``, which has readers, not in
    ``error``, which the runner writes first and the grader dict then shadows.
    """
    row = _drive_runner(monkeypatch, tmp_path, "python -c \"print('ok')\"",
                        OSError(13, "Permission denied"))
    assert "error" not in row or not str(row["error"]).startswith("OSError"), row
    assert "Permission denied" in row["refusal"], row


# --- entrance 2: behavior_bench.grade_behavior -------------------------------


@pytest.mark.parametrize("failure", HOST_FAILURES)
def test_the_python_behavior_grader_the_host_could_not_run_is_no_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: BaseException
) -> None:
    def unable(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise failure

    monkeypatch.setattr(behavior_bench.subprocess, "run", unable)
    graded = behavior_bench.grade_behavior(
        {"grader": {"type": "python_behavior", "cases": [{"call": "f()"}]}}, tmp_path
    )
    assert graded["passed"] is None, f"a host failure was graded as the agent's failure: {graded}"
    assert graded["grading_refused"] is True, graded
    assert graded["grader_type"] == "python_behavior", graded
    assert set(graded) == NO_RESULT_KEYS, graded


# --- the report still keeps the third verdict apart -------------------------


def test_a_legacy_refusal_is_counted_as_a_refusal_not_as_a_graded_row() -> None:
    """The row the fix produces must reach a reader, or it is M8-T81 again."""
    task = _legacy_task("python -c \"print('ok')\"")
    refusal = bench_tasks.grader_unable("command", OSError(2, "cannot start"))
    row = {"task_id": "legacy-verify", "category": "verify", "status": "completed",
           "claimed_complete": True, **refusal}
    metrics = build_report([task], [row])["metrics"]
    assert metrics["grading_refusal_count"] == 1, metrics
    assert metrics["gradable_task_count"] == 0, metrics


# --- the census that stops a third entrance from opening --------------------


def _production_sources() -> list[tuple[str, ast.Module]]:
    out: list[tuple[str, ast.Module]] = []
    for path in sorted((REPO_ROOT / "minicc").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        out.append((path.relative_to(REPO_ROOT).as_posix(),
                    ast.parse(path.read_text(encoding="utf-8"))))
    return out


def _names_a_host_failure(handler: ast.ExceptHandler) -> bool:
    """Does this handler catch the pair that means "the host could not run it"?"""
    if handler.type is None:
        return False
    for node in ast.walk(handler.type):
        if isinstance(node, ast.Name) and node.id == "OSError":
            return True
        if isinstance(node, ast.Attribute) and node.attr == "TimeoutExpired":
            return True
    return False


def _writes_a_passed_verdict(node: ast.AST) -> bool:
    """Every syntax production uses to book a verdict on a result row."""
    for sub in ast.walk(node):
        if isinstance(sub, (ast.Assign, ast.AnnAssign)):
            targets = sub.targets if isinstance(sub, ast.Assign) else [sub.target]
            for target in targets:
                if (isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant)
                        and target.slice.value == "passed"
                        and isinstance(sub.value, ast.Constant) and sub.value.value in (True, False)):
                    return True
        if isinstance(sub, ast.Dict):
            for key, value in zip(sub.keys, sub.values):
                if (isinstance(key, ast.Constant) and key.value == "passed"
                        and isinstance(value, ast.Constant) and value.value in (True, False)):
                    return True
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == "update":
            for kw in sub.keywords:
                if (kw.arg == "passed" and isinstance(kw.value, ast.Constant)
                        and kw.value.value in (True, False)):
                    return True
    return False


def _host_failures_written_as_verdicts(sources: list[tuple[str, ast.Module]]) -> list[str]:
    sites: list[str] = []
    for name, tree in sources:
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and _names_a_host_failure(node):
                if any(_writes_a_passed_verdict(statement) for statement in node.body):
                    sites.append(f"{name}:{node.lineno}")
    return sites


def test_no_exception_handler_for_a_host_failure_emits_a_verdict() -> None:
    """``except (OSError, TimeoutExpired)`` means nobody looked at the work."""
    sites = _host_failures_written_as_verdicts(_production_sources())
    assert sites == [], f"a host failure is being reported as the agent's failure: {sites}"


@pytest.mark.parametrize("planted,claim", [
    ("def g(t):\n    try:\n        pass\n    except OSError:\n        t['passed'] = False\n",
     "subscript assignment"),
    ("def g():\n    try:\n        pass\n    except (OSError, subprocess.TimeoutExpired):\n"
     "        return {'passed': False, 'grader_type': 'x'}\n", "dict literal"),
    ("def g(entry):\n    try:\n        pass\n    except subprocess.TimeoutExpired:\n"
     "        entry.update(passed=False)\n", "keyword update"),
])
def test_the_host_failure_census_reads_all_three_ways_to_write_a_verdict(
    planted: str, claim: str
) -> None:
    """Reverse control: the census above must not be silently blind to a shape.

    The site is counted, never pinned to a line number - a comment above the
    handler would move the line and make this gate report a false red.
    """
    sites = _host_failures_written_as_verdicts([("planted.py", ast.parse(planted))])
    assert len(sites) == 1 and sites[0].startswith("planted.py:"), (
        f"{claim} is not detected exactly once: {sites}"
    )


def test_the_census_is_not_matching_a_handler_that_only_refuses() -> None:
    """The other side of the control: the fixed shape must read as clean."""
    clean = (
        "import subprocess\n"
        "def g(entry, exc):\n"
        "    try:\n"
        "        pass\n"
        "    except (OSError, subprocess.TimeoutExpired) as exc:\n"
        "        entry.update(grader_unable('command', exc))\n"
    )
    assert _host_failures_written_as_verdicts([("clean.py", ast.parse(clean))]) == []


def test_a_verdict_written_outside_a_host_handler_is_not_flagged() -> None:
    """An agent that never claimed completion is its own case, not a host fault."""
    legit = (
        "def g(entry):\n"
        "    if entry['status'] != 'completed':\n"
        "        entry.update(passed=False, grader_type='command')\n"
    )
    assert _host_failures_written_as_verdicts([("legit.py", ast.parse(legit))]) == []
