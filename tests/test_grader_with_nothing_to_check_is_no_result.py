"""M8-T90: a contract that names nothing to check judged nobody - refuse it.

Measured on ``2a6dd09`` by calling the shipped producers directly:

* ``grade_command_contract`` with ``{"command": ""}`` or ``{"command": "   "}``
  returned ``{'passed': True, 'grader_type': 'command_contract', 'exit_code': 0}`` -
  ``cmd /c ""`` exits 0, the marker is printed, and an empty workspace is declared
  correct. This is the command twin of the ``files=[]`` vacuous pass M8-T87 found for
  ``file_contract`` (there it was guarded only in the metric; the producer still said pass).
* ``grade_command_contract`` with no ``command`` key returned ``passed=False`` - the
  grader could not read the spec, yet the failure was booked on the agent, which is
  exactly the M8-T83 class.

Both shapes mean "nobody looked at this workspace", so both now answer NO-RESULT
through ``_no_result``, and the refusal happens before the grader subprocess is
spawned. ``GRADER_TYPES`` is the shipped list of contract kinds, so the tables below
derive their producer list from it: a third contract type cannot skip this test.
"""

from __future__ import annotations

import pytest

import minicc.bench_tasks as bench_tasks
from minicc.benchmarks import build_report

NO_RESULT_KEYS = {"passed", "grader_type", "grading_refused", "refusal"}

# (grader type, the spec key that carries the work, shapes that carry none of it)
EMPTY_SHAPES = [
    ("file_contract", "files", [
        ("missing", {"type": "file_contract"}),
        ("empty-list", {"type": "file_contract", "files": []}),
        ("null-list", {"type": "file_contract", "files": None}),
    ]),
    ("command_contract", "command", [
        ("missing", {"type": "command_contract"}),
        ("empty-string", {"type": "command_contract", "command": ""}),
        ("blank-string", {"type": "command_contract", "command": "   "}),
    ]),
]

EMPTY_CASES = [
    pytest.param(grader_type, spec, id=f"{grader_type}-{shape}")
    for grader_type, _key, shapes in EMPTY_SHAPES
    for shape, spec in shapes
]


@pytest.mark.parametrize("grader_type,spec", EMPTY_CASES)
def test_a_contract_that_names_nothing_to_check_is_no_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path, grader_type: str, spec: dict
) -> None:
    def spawn(*args: object, **kwargs: object) -> object:
        raise AssertionError("an empty spec must be refused before any grader subprocess runs")

    monkeypatch.setattr(bench_tasks, "_run_grader", spawn)
    graded = bench_tasks.grade_v2({"grader": spec}, tmp_path, grader_dir=tmp_path / "g")
    assert graded["passed"] is None, (
        f"a {grader_type} spec with nothing to check produced a verdict: {graded}"
    )
    assert graded["grading_refused"] is True, graded
    assert graded["grader_type"] == grader_type, graded
    assert spec_key_named(graded["refusal"], grader_type), graded
    assert set(graded) <= NO_RESULT_KEYS, graded


def spec_key_named(refusal: object, grader_type: str) -> bool:
    """The refusal has to say which half of the spec was empty, or it is a shrug."""
    text = str(refusal or "")
    expected = {"file_contract": "files", "command_contract": "command"}[grader_type]
    return expected in text


def test_every_shipped_contract_kind_is_covered_by_the_empty_spec_table() -> None:
    """Derive the population from the shipped constant, never from a hand-copied list."""
    covered = {grader_type for grader_type, _key, _specs in EMPTY_SHAPES}
    assert covered == set(bench_tasks.GRADER_TYPES), (
        f"GRADER_TYPES says {sorted(bench_tasks.GRADER_TYPES)}, the table covers {sorted(covered)}"
    )


def test_a_real_contract_still_reaches_a_verdict(tmp_path) -> None:
    """Control: the refusal must not become a way to erase green either.

    One listed file and one runnable command are real work checked, so they get a
    ``passed`` value and no refusal attached.
    """
    (tmp_path / "notes.md").write_text("hello\n", encoding="utf-8")
    graded = bench_tasks.grade_file_contract(
        {"grader": {"type": "file_contract", "files": [{"path": "notes.md", "exists": True}]}},
        tmp_path, grader_dir=tmp_path / "g",
    )
    assert graded["passed"] is True, graded
    assert not graded.get("grading_refused"), graded
    assert graded["case_count"] == 1, graded


def test_a_real_command_contract_still_reaches_a_verdict(tmp_path) -> None:
    graded = bench_tasks.grade_command_contract(
        {"grader": {"type": "command_contract", "command": '{python} -c "print(1)"'}},
        tmp_path, grader_dir=tmp_path / "g",
    )
    assert graded["passed"] is True, graded
    assert not graded.get("grading_refused"), graded


def test_a_refused_empty_contract_reaches_the_report_as_a_refusal(tmp_path) -> None:
    """No-RESULT is only honest if a reader exists; M8-T81's rule again."""
    graded = bench_tasks.grade_command_contract(
        {"grader": {"type": "command_contract", "command": ""}}, tmp_path, grader_dir=tmp_path / "g"
    )
    task = {"id": "empty-command", "category": "verify",
            "prompt": "回答任意内容。", "grader": {"type": "command_contract", "command": ""}}
    row = {"task_id": "empty-command", "category": "verify", "status": "completed",
           "claimed_complete": True, **graded}
    metrics = build_report([task], [row])["metrics"]
    assert metrics["grading_refusal_count"] == 1, metrics
    assert metrics["gradable_task_count"] == 0, metrics
    assert metrics["false_completion_rate"] is None, metrics
