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

M8-T87 is the other half of the same promise: the count has to be as strong as
the human judgement it replaces. The record at
`docs/ROADMAP_TO_PRODUCT.md:2427` required "passed=true with a clean case and
exit count", but a ``file_contract`` with an empty ``files`` list prints its own
completion marker for zero cases, so a bare ``passed is True`` would credit the
reviewer with a false negative that nobody ever disproved.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import minicc.bench_tasks as bench_tasks
import minicc.benchmarks as benchmarks

REPO_ROOT = Path(__file__).resolve().parent.parent


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


# --- M8-T87: a pass over zero cases is not a pass over the work ---------------


def test_an_oracle_that_checked_zero_cases_is_not_a_false_negative() -> None:
    vacuous = _capped("empty-contract", {"passed": True, "case_count": 0})
    checked = _capped("one-case", {"passed": True, "case_count": 1})
    assert _report([vacuous])["metrics"]["reviewer_false_negative_count"] == 0
    assert _report([vacuous, checked])["metrics"]["reviewer_false_negative_count"] == 1


def test_a_missing_case_count_is_not_read_as_zero_cases() -> None:
    """``command_contract`` oracles carry no case count: absence is not vacuity."""
    metrics = _report([_capped("cmd", {"passed": True, "exit_code": 0})])["metrics"]
    assert metrics["reviewer_false_negative_count"] == 1, metrics


@pytest.mark.parametrize("broken", [True, "3", -1, None, 0.5])
def test_a_case_count_that_is_not_a_measurement_does_not_qualify(broken: object) -> None:
    metrics = _report([_capped("t", {"passed": True, "case_count": broken})])["metrics"]
    assert metrics["reviewer_false_negative_count"] == 0, broken


def test_the_real_producer_refuses_an_empty_contract(tmp_path: Path) -> None:
    """M8-T87 guarded the metric; M8-T90 closes the same vacuous pass at the source.

    The claim changed: on ``2a6dd09`` this producer handed back ``passed=True`` with
    ``case_count == 0`` for ``files=[]``, so the metric guard was the only thing
    standing. Now the contract is refused before the grader runs, and the metric
    still refuses a hand-built or legacy oracle that reports zero cases.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()
    graded = bench_tasks.grade_file_contract(
        {"id": "t", "grader": {"type": "file_contract", "files": []}},
        workspace, grader_dir=tmp_path / "graders",
    )
    assert graded["passed"] is None and graded["grading_refused"] is True, graded
    assert _report([_capped("t", graded)])["metrics"]["reviewer_false_negative_count"] == 0
    legacy = _capped("t", {"passed": True, "case_count": 0})
    assert _report([legacy])["metrics"]["reviewer_false_negative_count"] == 0


def test_the_zero_case_rule_reads_a_key_the_producer_really_emits() -> None:
    """Otherwise the rule is my invention: ``case_count`` must come out of a grader."""
    tree = ast.parse((REPO_ROOT / "minicc" / "bench_tasks.py").read_text(encoding="utf-8"))
    emitted: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("grade_"):
            for inner in ast.walk(node):
                if isinstance(inner, ast.Dict):
                    emitted.update(key.value for key in inner.keys
                                   if isinstance(key, ast.Constant) and isinstance(key.value, str))
    assert "case_count" in emitted, sorted(emitted)


def test_the_zero_case_exclusion_is_told_to_the_reader() -> None:
    text = benchmarks.markdown_report(_report([_capped("t", {"passed": True, "case_count": 0})]))  # type: ignore[arg-type]
    assert "zero cases" in text, text
