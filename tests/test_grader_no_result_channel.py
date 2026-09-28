"""M8-T80: the grader's third verdict - cannot judge - must reach the report.

The file-contract grader exits 2 when it refuses to grade (M8-T58: a workspace
file it cannot decode, or a contract path that escapes the workspace). Until
this batch the host folded any non-zero exit into ``passed=False``, which means
a refusal was charged to the agent: ``build_report`` keeps ``passed=None`` rows
out of ``gradable`` on purpose, so the correct value already had a channel and
nobody was writing into it.

The controls here are the other half: a real failure must stay False, and a real
pass must stay True - otherwise "cannot judge" would just be a way to make
red disappear.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

import minicc.bench_tasks as bench_tasks

MARKER = "评分标记"


def _task(files: list[dict[str, Any]]) -> dict[str, Any]:
    return {"id": "t", "grader": {"type": "file_contract", "files": files}}


def _file_grade(task: dict[str, Any], workspace: Path, grader_dir: Path) -> dict[str, Any]:
    return bench_tasks.grade_file_contract(task, workspace, grader_dir=grader_dir)


def test_a_file_the_grader_cannot_decode_refuses_instead_of_failing(
    tmp_path: Path
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    # Valid in a legacy codepage, invalid utf-8 - exactly what M8-T58 closed.
    (workspace / "notes.txt").write_bytes(MARKER.encode("gbk"))
    graded = _file_grade(
        _task([{"path": "notes.txt", "not_contains": MARKER}]), workspace, tmp_path / "graders"
    )
    assert graded["exit_code"] == 2, graded
    assert graded["passed"] is None, f"a refusal was graded as a verdict: {graded}"
    assert graded["grading_refused"] is True
    assert "utf-8" in graded["refusal"], graded["refusal"]


def test_a_contract_path_that_escapes_the_workspace_is_also_no_result(
    tmp_path: Path
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    graded = _file_grade(
        _task([{"path": "../outside.txt", "exists": True}]), workspace, tmp_path / "graders"
    )
    assert graded["exit_code"] == 2, graded
    assert graded["passed"] is None, graded
    assert "escapes" in graded["refusal"], graded["refusal"]


def test_a_genuine_pass_still_reports_true(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "report.md").write_text(f"# 报告\n{MARKER}\n", encoding="utf-8")
    graded = _file_grade(
        _task([{"path": "report.md", "contains": MARKER}]), workspace, tmp_path / "graders"
    )
    assert graded["passed"] is True, graded
    assert "grading_refused" not in graded


def test_a_genuine_failure_still_reports_false(tmp_path: Path) -> None:
    """The refusal channel must not become a way to make red disappear."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "report.md").write_text("# 报告\n没有标记\n", encoding="utf-8")
    graded = _file_grade(
        _task([{"path": "report.md", "contains": MARKER}]), workspace, tmp_path / "graders"
    )
    assert graded["passed"] is False, graded
    assert "grading_refused" not in graded


@pytest.mark.parametrize("grader_name", ["grade_file_contract", "grade_command_contract"])
def test_exit_2_maps_to_no_result_for_both_graders(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, grader_name: str
) -> None:
    """The host mapping, isolated from which reason made the grader refuse."""

    def refused(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=2, stdout="", stderr="refusal line")

    monkeypatch.setattr(bench_tasks, "_run_grader", refused)
    # A spec with work in it: since M8-T90 an empty files list / missing command is
    # refused before the subprocess, which would test this mapping with the wrong door.
    task = {"grader": (
        {"type": "file_contract", "files": [{"path": "a.txt", "exists": True}]}
        if grader_name == "grade_file_contract"
        else {"type": "command_contract", "command": "python x.py"}
    )}
    graded = getattr(bench_tasks, grader_name)(task, tmp_path, grader_dir=tmp_path / "graders")
    assert graded["passed"] is None, graded
    assert graded["grading_refused"] is True
    assert graded["refusal"] == "refusal line"
    assert graded["exit_code"] == 2


def test_a_nonzero_exit_that_is_not_two_stays_a_verdict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def failed(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(bench_tasks, "_run_grader", failed)
    graded = bench_tasks.grade_file_contract(
        _task([{"path": "a.txt", "exists": True}]), tmp_path, grader_dir=tmp_path / "graders"
    )
    assert graded["passed"] is False, graded
    assert "grading_refused" not in graded


def test_the_refusal_is_recorded_in_the_result_row(tmp_path: Path) -> None:
    """A no-result must be auditable: the row keeps the reason and the exit code.

    ``build_report`` reads ``passed``/``status``; nothing may drop the reason on
    the way, or the suite ends up with unexplained non-gradable rows.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "notes.txt").write_bytes(MARKER.encode("gbk"))
    graded = _file_grade(
        _task([{"path": "notes.txt", "not_contains": MARKER}]), workspace, tmp_path / "graders"
    )
    assert set(graded) >= {"passed", "grader_type", "grading_refused", "exit_code", "refusal"}
    assert json.dumps(graded, ensure_ascii=False), "the refusal row must be serialisable"
    assert graded["grader_type"] == "file_contract"
