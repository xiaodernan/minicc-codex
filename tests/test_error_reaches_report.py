"""M8-T85: a failed/interrupted task must report WHY, not just "failed".

``run_benchmark`` records the reason a failed task did not finish in
``entry["error"]`` (timeout / Exception / agent error). An operator abort
(M8-T113) uses the refusal channel instead, because nothing was judged.
``build_report`` rebuilds every row key-by-key and returns
``report["results"]`` as those rows, so a field it does not copy is invisible in
BOTH the structured row and the markdown table - the exact defect M8-T81 closed
for ``grading_refused``.  Before this gate ``error`` was dropped: a human or a
CLI reading the report saw ``failed`` with no cause, and the reason only ever
survived in the raw results JSON that tests read directly.

These gates are behavioural: they assert the recorded reason reaches the rendered
row and the printed table cell, and that a completed task is NOT polluted with
an empty error bracket.  The reverse control lives in the mutation witness (drop
the row copy -> these go red), not in a key-name assertion.
"""

from __future__ import annotations

from minicc.benchmarks import build_report, markdown_report


def _row_and_md(result: dict, task: dict | None = None):
    report = build_report([task or {"id": result["task_id"], "category": "x"}], [result])
    row = report["results"][0]
    md_line = next(line for line in markdown_report(report).splitlines()
                   if line.startswith(f"| {result['task_id']} "))
    return row, md_line


def test_a_failed_task_carries_its_recorded_reason_into_the_report_row():
    row, md_line = _row_and_md(
        {"task_id": "t", "status": "failed", "passed": False, "error": "task timeout > 60s"})
    assert row["error"] == "task timeout > 60s", row
    # The bare "failed with no cause" shape must be gone from the printed table too.
    assert "task timeout > 60s" in md_line, md_line


def test_an_interrupted_task_reports_its_exception_name():
    """M8-T113 moved this row's reason from ``error`` to ``refusal``.

    The runner no longer books a verdict for an interrupt (nothing was judged),
    so the reason arrives through the refusal channel. The gate keeps asking the
    report to print the name rather than a bare REFUSED with no cause.
    """
    row, md_line = _row_and_md(
        {"task_id": "t", "status": "interrupted", "passed": None,
         "grading_refused": True, "refusal": "KeyboardInterrupt"})
    assert row["refusal"] == "KeyboardInterrupt", row
    assert "REFUSED" in md_line and "KeyboardInterrupt" in md_line, md_line


def test_a_completed_task_is_not_polluted_with_an_empty_error_cell():
    row, md_line = _row_and_md(
        {"task_id": "ok", "status": "completed", "passed": True})
    assert row["error"] is None, row
    assert "[" not in md_line, md_line


def test_the_error_is_bounded_like_the_writer_bounds_it():
    long = "e" * 400
    row, _md = _row_and_md(
        {"task_id": "t", "status": "failed", "passed": False, "error": long})
    assert row["error"] == "e" * 200, len(row["error"])
