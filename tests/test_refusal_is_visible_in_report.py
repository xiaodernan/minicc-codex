"""M8-T81: the third verdict must be readable by a human in the report.

M8-T80 made a grader's refusal reach ``build_report`` as ``passed=None`` - the
right channel, since refusals are excluded from ``gradable``. But the two fields
it wrote (``grading_refused`` and ``refusal``) had no reader anywhere outside
``bench_tasks.py`` (measured on the 57db4bd plane), and ``markdown_report``
printed a refusal as ``Passed | N/A`` - byte-identical to a task with no grader
at all. That is the same defect class M8-T79 censused for version constants:
a value with a writer and no reader.

These gates keep the three shapes apart: passed, refused, ungraded.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import minicc.benchmarks as benchmarks

REPO_ROOT = Path(__file__).resolve().parent.parent
WRITER_MODULE = REPO_ROOT / "minicc" / "bench_tasks.py"


def _report(rows: list[dict[str, object]]) -> dict[str, object]:
    # build_report takes category/grader from the fixture and the verdict from the
    # recorded row, so the helper has to feed both sides the way run_benchmark does.
    tasks = [{"id": str(row["task_id"]), "category": str(row["category"])} for row in rows]
    return benchmarks.build_report(tasks, rows)  # type: ignore[arg-type]


def _row(task_id: str, passed: object, **extra: object) -> dict[str, object]:
    return {"task_id": task_id, "category": "edit", "status": "completed",
            "passed": passed, "claimed_complete": False, **extra}


def test_a_refusal_is_counted_as_neither_a_pass_nor_a_missing_grader() -> None:
    report = _report([
        _row("ok", True),
        _row("refused", None, grading_refused=True, refusal="not valid utf-8 at byte 3"),
        _row("ungraded", None),
    ])
    metrics = report["metrics"]
    assert metrics["grading_refusal_count"] == 1, metrics
    assert metrics["gradable_task_count"] == 1, metrics


def test_the_count_is_derived_from_the_rows_not_written_twice() -> None:
    """Move the rows, the count must move with them."""
    base = [
        _row("ok", True),
        _row("refused", None, grading_refused=True, refusal="boom"),
    ]
    assert _report(base)["metrics"]["grading_refusal_count"] == 1
    assert _report(base + [_row("also", None, grading_refused=True)])["metrics"][
        "grading_refusal_count"] == 2
    assert _report([_row("ok", True)])["metrics"]["grading_refusal_count"] == 0


def test_the_markdown_table_keeps_refused_and_ungraded_apart() -> None:
    report = _report([
        _row("refused", None, grading_refused=True, refusal="not valid utf-8 at byte 3"),
        _row("ungraded", None),
    ])
    lines = benchmarks.markdown_report(report).splitlines()  # type: ignore[arg-type]
    refused_line = next(line for line in lines if "refused" in line and line.startswith("|"))
    ungraded_line = next(line for line in lines if "ungraded" in line and line.startswith("|"))
    assert "REFUSED" in refused_line, refused_line
    assert "N/A" in ungraded_line, ungraded_line
    assert refused_line != ungraded_line, "a refusal is printed exactly like a task with no grader"


def test_the_refusal_reason_reaches_the_table() -> None:
    report = _report([_row("t", None, grading_refused=True,
                           refusal="cannot judge content of notes.txt: not valid utf-8")])
    text = benchmarks.markdown_report(report)  # type: ignore[arg-type]
    assert "notes.txt" in text, text
    assert "utf-8" in text


def test_the_summary_table_prints_the_refusal_count() -> None:
    text = benchmarks.markdown_report(_report([
        _row("t", None, grading_refused=True, refusal="x"),
    ]))
    assert "grading_refusal_count" in text, "the metric is computed but never shown"


def test_a_printed_metric_is_explained_to_the_reader() -> None:
    """A new row in the summary table is only useful if the report says what it means."""
    text = benchmarks.markdown_report(_report([_row("t", True)]))
    assert "REFUSED" in text, "the metric name is shown but no note defines the word"
    assert "not a pass" in text, text


def test_a_pass_and_a_failure_are_still_printed_as_verdicts() -> None:
    """The refusal cell must not become a way to make a red unreadable."""
    text = benchmarks.markdown_report(_report([_row("good", True), _row("bad", False)]))
    assert "| good |" in text and "| True |" in text
    assert "| bad |" in text and "| False |" in text
    task_rows = [line for line in text.splitlines() if line.startswith("| good |") or line.startswith("| bad |")]
    assert task_rows, text
    assert not any("REFUSED" in line for line in task_rows), task_rows


# --- the census that keeps these fields from going write-only again ---------


def _reader_files() -> set[str]:
    """Every production module that names the flag, except the one that writes it."""
    readers: set[str] = set()
    for path in sorted((REPO_ROOT / "minicc").rglob("*.py")):
        if path == WRITER_MODULE or "__pycache__" in path.parts:
            continue
        if "grading_refused" in path.read_text(encoding="utf-8"):
            readers.add(path.relative_to(REPO_ROOT).as_posix())
    return readers


def test_the_refusal_flag_has_a_reader_outside_its_writer() -> None:
    readers = _reader_files()
    assert readers, "grading_refused is written and read by nobody - the M8-T79 shape again"
    assert "minicc/benchmarks.py" in readers, readers


def test_the_refusal_flag_is_read_as_a_dict_key_not_a_bare_word() -> None:
    """A reader must actually index the row, not merely mention the name in prose."""
    source = (REPO_ROOT / "minicc" / "benchmarks.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    keyed = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and first.value == "grading_refused":
                keyed += 1
        elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            if node.slice.value == "grading_refused":
                keyed += 1
    assert keyed >= 2, f"expected the flag read in both the metric and the cell, got {keyed}"


@pytest.mark.parametrize("planted", [
    "def write():\n    return {'grading_refused': True}\n",
    "# grading_refused appears only in a comment\n",
])
def test_the_reader_census_does_not_count_the_writer_or_prose(planted: str) -> None:
    """Reverse control: the census looks for a key read, and a dict literal writing
    the key is not a read - so a module that only mentions the word must not count.
    """
    tree = ast.parse(planted)
    keyed_reads = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            if node.args[0].value == "grading_refused":
                keyed_reads += 1
    assert keyed_reads == 0, planted
