"""M8-T86: a value that is computed must be a value somebody can read.

Measured on the 3d75d39 plane: ``markdown_report`` printed its metrics from a
hand-written tuple sitting beside ``build_report``'s metrics dict, and no gate
compared the two. They agreed (15 keys / 15 keys) only because the previous
author remembered to edit both places - the same write-only-on-one-side class
M8-T79, M8-T80 and M8-T81 recorded. ``objective_oracle`` was written by the
runner and read by tests straight off the results JSON, but
``build_report`` rebuilds every row key by key and dropped it, so the
diagnostic the producer wrote for a human review ("a reviewer false negative
looks exactly like missing work") could never be aggregated anywhere.

These gates hold both directions: every metric key gets a table row, a key that
nobody hand-copied still gets a row, and the false-negative count is derived
from the rows the report itself carries.
"""

from __future__ import annotations

import minicc.benchmarks as benchmarks


def _report(rows: list[dict[str, object]]) -> dict[str, object]:
    tasks = [{"id": str(row["task_id"]), "category": str(row["category"])} for row in rows]
    return benchmarks.build_report(tasks, rows)  # type: ignore[arg-type]


def _capped(task_id: str, oracle: object, **extra: object) -> dict[str, object]:
    """A task the completion judge capped: recorded failed, never graded."""
    return {"task_id": task_id, "category": "edit", "status": "failed", "passed": False,
            "claimed_complete": False, "error": "completion judge did not converge",
            "objective_oracle": oracle, **extra}


def _metric_keys(markdown: str) -> list[str]:
    lines = markdown.splitlines()
    keys: list[str] = []
    for line in lines[lines.index("| --- | ---: |") + 1:]:
        if not line.startswith("|"):
            break
        keys.append(line.split("|")[1].strip())
    return keys


def test_the_objective_oracle_survives_the_row_rebuild() -> None:
    report = _report([_capped("t", {"passed": True, "case_count": 3})])
    row = report["results"][0]  # type: ignore[index]
    assert row["objective_oracle"] == {"passed": True, "case_count": 3}, row
    assert row["passed"] is False, "the diagnostic must not rewrite the verdict"


def test_a_non_dict_oracle_is_not_carried_as_a_verdict() -> None:
    for planted in ("True", 1, ["passed"], None):
        row = _report([_capped("t", planted)])["results"][0]  # type: ignore[index]
        assert row["objective_oracle"] is None, planted


def test_the_false_negative_count_moves_with_the_rows() -> None:
    """Only a recorded failure whose objective grader says passed counts."""
    agree = _capped("no-argument", {"passed": False})
    blind = _capped("grader-broke", {"error": "ValueError: bad spec"})

    def count(rows: list[dict[str, object]]) -> int:
        return _report(rows)["metrics"]["reviewer_false_negative_count"]  # type: ignore[index]

    assert count([agree, blind]) == 0
    assert count([_capped("t", {"passed": True})]) == 1
    assert count([_capped("a", {"passed": True}), _capped("b", {"passed": True}), agree]) == 2


def test_a_row_the_reviewer_never_doubled_does_not_count() -> None:
    """The count is about disagreement, so a graded pass and an ungraded task are 0."""
    graded = {"task_id": "g", "category": "edit", "status": "completed", "passed": True,
              "objective_oracle": {"passed": True}}
    ungraded = {"task_id": "u", "category": "edit", "status": "completed", "passed": None,
                "objective_oracle": {"passed": True}}
    metrics = _report([graded, ungraded])["metrics"]
    assert metrics["reviewer_false_negative_count"] == 0, metrics
    assert _report([])["metrics"]["reviewer_false_negative_count"] == 0


def test_every_computed_metric_gets_a_row_in_the_table() -> None:
    report = _report([_capped("t", {"passed": True}),
                      {"task_id": "k", "category": "edit", "status": "completed",
                       "passed": True, "claimed_complete": True}])
    keys = _metric_keys(benchmarks.markdown_report(report))  # type: ignore[arg-type]
    assert set(keys) == set(report["metrics"]), {  # type: ignore[arg-type]
        "missing": set(report["metrics"]) - set(keys),  # type: ignore[index]
        "extra": set(keys) - set(report["metrics"]),  # type: ignore[index]
    }
    assert len(keys) == len(set(keys)), "a metric printed twice has two possible values"


def test_a_metric_that_nobody_hand_copied_is_still_printed() -> None:
    """The reverse control: a key added to the metrics dict alone must reach the table."""
    report = _report([{"task_id": "t", "category": "edit", "status": "completed", "passed": True}])
    report["metrics"]["zzz_metric_added_only_to_the_dict"] = 7  # type: ignore[index]
    keys = _metric_keys(benchmarks.markdown_report(report))  # type: ignore[arg-type]
    assert "zzz_metric_added_only_to_the_dict" in keys, keys
    assert "| zzz_metric_added_only_to_the_dict | 7 |" in benchmarks.markdown_report(report)


def test_the_false_negative_count_is_visible_to_a_human() -> None:
    text = benchmarks.markdown_report(_report([_capped("capped-task", {"passed": True})]))  # type: ignore[arg-type]
    assert "| reviewer_false_negative_count | 1 |" in text, text
    assert "capped-task" in text


def test_the_new_aggregate_is_explained_to_the_reader() -> None:
    text = benchmarks.markdown_report(_report([_capped("t", {"passed": True})]))  # type: ignore[arg-type]
    line = next(note for note in text.splitlines()
                if "reviewer_false_negative_count" in note and note.startswith("- "))
    assert "diagnostic" in line, line
    assert "suite score" in line, line
