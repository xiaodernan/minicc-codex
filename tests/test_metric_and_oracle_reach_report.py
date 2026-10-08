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
    # The passing oracles here carry no case count, so since M8-T93 they need the grader
    # name that justifies trusting them - exactly the work this branch used to do silently.
    assert count([_capped("t", {"passed": True}, grader_type="command_contract")]) == 1
    assert count([_capped("a", {"passed": True}, grader_type="command_contract"),
                  _capped("b", {"passed": True}, grader_type="command_contract"), agree]) == 2
    assert count([_capped("anon", {"passed": True})]) == 0, (
        "an oracle that names no grader must not borrow a shipped grader's justification"
    )


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


def _metrics_dict_literal() -> dict[str, ast.expr]:
    """The metrics dict ``build_report`` returns, as ``{key: value-node}``."""
    tree = ast.parse((REPO_ROOT / "minicc" / "benchmarks.py").read_text(encoding="utf-8"))
    builder = next(node for node in ast.walk(tree)
                   if isinstance(node, ast.FunctionDef) and node.name == "build_report")
    for node in ast.walk(builder):
        if not isinstance(node, ast.Dict):
            continue
        keys = {key.value for key in node.keys if isinstance(key, ast.Constant)}
        if {"pass_at_1", "acceptance_success_rate"} <= keys:
            return {key.value: value for key, value in zip(node.keys, node.values)
                    if isinstance(key, ast.Constant)}
    raise AssertionError("build_report no longer builds a metrics dict holding both acceptance names")


def test_the_two_acceptance_names_are_one_definition() -> None:
    """M8-T185: one number, two published names, one expression.

    ``pass_at_1`` and ``acceptance_success_rate`` are the same quantity -
    docs/BENCHMARK_EVALUATION.md lists them on one row - and for the whole life of
    the report they were two separately typed copies of
    ``round(len(passed) / len(gradable), 4)``. Nothing in the repository reads the
    second name (census in the batch record), so an edit to either copy would
    have published two different numbers under two names with no reader and no
    gate to object. Both keys must therefore read one local definition.
    """
    values = _metrics_dict_literal()
    for name in ("pass_at_1", "acceptance_success_rate"):
        node = values[name]
        assert isinstance(node, ast.Name), (
            f"{name} computes the acceptance rate in place again; it must read the one "
            "local definition so the two names cannot drift apart"
        )
    assert values["pass_at_1"].id == values["acceptance_success_rate"].id, (
        f"the two acceptance names read two different locals: "
        f"{values['pass_at_1'].id!r} and {values['acceptance_success_rate'].id!r}"
    )


def test_the_two_acceptance_names_never_disagree() -> None:
    """The behavioural half: whatever the rows say, the two keys say the same thing."""
    graded = {"id": "t", "category": "edit",
              "grader": {"type": "file_contract", "path": "a", "contains": "b"}}
    shapes = [
        [{"task_id": "t", "status": "completed", "passed": True}],
        [{"task_id": "t", "status": "completed", "passed": False}],
        [{"task_id": "t", "status": "completed", "passed": None, "grading_refused": True}],
        [{"task_id": "t", "status": "not_run"}],
        [],
    ]
    for rows in shapes:
        metrics = benchmarks.build_report([graded], rows)["metrics"]
        assert metrics["pass_at_1"] == metrics["acceptance_success_rate"], (rows, metrics)


def test_the_third_verdict_is_counted_and_not_called_a_refusal() -> None:
    """M8-T184: "nobody judged this workspace" is two different stories.

    ``gradable`` is selected by ``passed is not None`` and the refusal count by
    ``grading_refused``. Those are different predicates, so a completed row whose
    task declares neither a grader nor a verify_command satisfies neither: the
    runner never writes ``passed`` for it at all. Until this column,
    ``grading_coverage`` was the only signal, and it reads identically for "the
    grader declined" and "there was nothing to grade with" - two situations with
    different owners, one being the run and one being the suite.
    """
    graded = {"id": "judged", "category": "edit",
              "grader": {"type": "file_contract", "path": "a", "contains": "b"}}
    refused_task = dict(graded, id="refused")
    plain = {"id": "no-grader", "category": "edit"}
    idle = {"id": "not-run", "category": "edit"}
    rows = [
        {"task_id": "judged", "category": "edit", "status": "completed", "passed": True},
        {"task_id": "refused", "category": "edit", "status": "completed", "passed": None,
         "grading_refused": True, "refusal": "grader exited 2"},
        {"task_id": "no-grader", "category": "edit", "status": "completed", "passed": None},
        {"task_id": "not-run", "category": "edit", "status": "not_run"},
    ]
    report = benchmarks.build_report([graded, refused_task, plain, idle], rows)
    metrics = report["metrics"]
    assert metrics["no_grader_count"] == 1
    assert metrics["grading_refusal_count"] == 1
    assert metrics["gradable_task_count"] == 1
    # The not_run row is not an executed row, so it belongs to none of the three.
    assert (metrics["gradable_task_count"] + metrics["grading_refusal_count"]
            + metrics["no_grader_count"]) == report["executed_count"] == 3
    # A refusal is not laundered into the new count, and vice versa.
    assert "| no_grader_count | 1 |" in benchmarks.markdown_report(report)


def test_the_shipped_legacy_suite_is_mostly_the_third_verdict() -> None:
    """The measured shape, not a hypothetical: 27 of 30 legacy tasks.

    A report of that suite reads ``pass_at_1 = 1.0`` beside
    ``grading_coverage = 0.1``, and before this column nothing in it said the 0.9
    was "no grader" rather than "the graders broke". Measured on a real run of
    ``--suite legacy`` under the fake provider: 27 rows completed, ungraded, and
    not one refusal among them. The synthetic results below are faithful to that
    run - a task with a grader carries a verdict, a task without one carries none,
    because that is what the runner writes.
    """
    tasks = benchmarks.load_tasks()
    assert len(tasks) == 30, len(tasks)
    results = [
        {"task_id": str(task["id"]), "status": "completed",
         **({"passed": True} if (isinstance(task.get("grader"), dict)
                                 or task.get("verify_command")) else {})}
        for task in tasks
    ]
    metrics = benchmarks.build_report(tasks, results)["metrics"]
    assert metrics["no_grader_count"] == 27, metrics
    assert metrics["grading_refusal_count"] == 0, metrics
    assert metrics["gradable_task_count"] == 3, metrics
    assert metrics["grading_coverage"] == 0.1, metrics
    # The three verdicts account for every executed row, exactly.
    report = benchmarks.build_report(tasks, results)
    assert (metrics["gradable_task_count"] + metrics["grading_refusal_count"]
            + metrics["no_grader_count"]) == report["executed_count"] == 30


def test_a_row_that_lost_its_verdict_is_not_reported_as_a_task_without_a_grader() -> None:
    """M8-T184: the count asks the task, so a damaged row stays silent.

    A resumed results file that lost its ``passed`` key produces a row that is
    ungraded, not refused, and *does* have a grader. Counting it as "no grader"
    would be a claim about the suite that the row cannot support - and the
    shorter expression, ``passed is None and not grading_refused``, would make
    exactly that claim. The three counts therefore stop short of ``executed_count``
    by one, which is the honest shape: the reader sees a gap instead of a lie.
    """
    tasks = [{"id": "graded", "category": "edit",
              "grader": {"type": "file_contract", "path": "a", "contains": "b"}},
             {"id": "plain", "category": "edit"}]
    results = [{"task_id": "graded", "status": "completed"},   # verdict lost
               {"task_id": "plain", "status": "completed"}]     # never had one
    report = benchmarks.build_report(tasks, results)
    metrics = report["metrics"]
    assert metrics["no_grader_count"] == 1, metrics
    assert metrics["gradable_task_count"] == 0, metrics
    assert metrics["grading_refusal_count"] == 0, metrics
    assert (metrics["gradable_task_count"] + metrics["grading_refusal_count"]
            + metrics["no_grader_count"]) == report["executed_count"] - 1, (
        "the damaged row must show up as a gap, not be absorbed into a count "
        "that would then describe the suite wrongly"
    )


def test_a_graded_row_is_never_also_counted_as_a_refusal() -> None:
    """The invariant the partition rests on, asserted rather than assumed.

    ``no_grader_count`` is defined as ``passed is None and not grading_refused``,
    so the three counts only partition the executed rows if no row is both
    graded and refused. The runner cannot produce that row - a refusal arrives
    through ``_no_result`` with ``passed=None`` - but ``build_report`` also reads
    resumed results JSON, and a hand-edited file could say both. If that ever
    happens the reader must see it as a broken report, not as a miscount.
    """
    graded = {"id": "both", "category": "edit",
              "grader": {"type": "file_contract", "path": "a", "contains": "b"}}
    clean = dict(graded, id="clean")
    rows = [
        {"task_id": "both", "category": "edit", "status": "completed",
         "passed": False, "grading_refused": True, "refusal": "grader exited 2"},
        {"task_id": "clean", "category": "edit", "status": "completed", "passed": True},
    ]
    metrics = benchmarks.build_report([graded, clean], rows)["metrics"]
    assert metrics["gradable_task_count"] == 2
    assert metrics["grading_refusal_count"] == 1
    assert metrics["no_grader_count"] == 0
    assert (metrics["gradable_task_count"] + metrics["grading_refusal_count"]
            + metrics["no_grader_count"]) != benchmarks.build_report(
                [graded, clean], rows)["executed_count"], (
        "a row that is both graded and refused breaks the partition; this report "
        "is the shape that must never reach a reader silently"
    )


def test_a_metric_that_nobody_hand_copied_is_still_printed() -> None:
    """The reverse control: a key added to the metrics dict alone must reach the table."""
    report = _report([{"task_id": "t", "category": "edit", "status": "completed", "passed": True}])
    report["metrics"]["zzz_metric_added_only_to_the_dict"] = 7  # type: ignore[index]
    keys = _metric_keys(benchmarks.markdown_report(report))  # type: ignore[arg-type]
    assert "zzz_metric_added_only_to_the_dict" in keys, keys
    assert "| zzz_metric_added_only_to_the_dict | 7 |" in benchmarks.markdown_report(report)


def test_the_false_negative_count_is_visible_to_a_human() -> None:
    # grader_type is what the count is about: since M8-T93 an oracle with no case count
    # is only trusted for a shipped grader, and command_contract is the one that reports none.
    text = benchmarks.markdown_report(_report([_capped(
        "capped-task", {"passed": True}, grader_type="command_contract")]))  # type: ignore[arg-type]
    assert "| reviewer_false_negative_count | 1 |" in text, text
    assert "capped-task" in text


def test_the_new_aggregate_is_explained_to_the_reader() -> None:
    text = benchmarks.markdown_report(_report([_capped(
        "t", {"passed": True}, grader_type="command_contract")]))  # type: ignore[arg-type]
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
    """A shipped command_contract oracle reports no count: absence is not vacuity."""
    metrics = _report([_capped("cmd", {"passed": True, "exit_code": 0},
                               grader_type="command_contract")])["metrics"]
    assert metrics["reviewer_false_negative_count"] == 1, metrics


@pytest.mark.parametrize("grader_type,expected", [
    ("command_contract", 1),      # shipped: its marker prints only after real work ran
    ("mystery_oracle", 0),        # unknown producer cannot borrow that trust
    (None, 0),                    # a row that never says who judged it
])
def test_an_oracle_without_a_case_count_is_trusted_only_for_a_shipped_grader(
    grader_type: str | None, expected: int
) -> None:
    """M8-T93: the trust branch is a claim about a grader, so it needs a name."""
    extra = {} if grader_type is None else {"grader_type": grader_type}
    metrics = _report([_capped("t", {"passed": True, "exit_code": 0}, **extra)])["metrics"]
    assert metrics["reviewer_false_negative_count"] == expected, (grader_type, metrics)


def test_the_trust_branch_asks_the_shipped_vocabulary_not_a_copied_list() -> None:
    """Otherwise the branch is a second hand-written copy of GRADER_TYPES.

    The gate looks for the structural pattern: ``GRADER_TYPES`` must be
    referenced as a Name/Attribute in a membership test (``in``/``not in``),
    not merely appear as a string literal in the function body.
    """
    tree = ast.parse((REPO_ROOT / "minicc" / "benchmarks.py").read_text(encoding="utf-8"))
    found = False
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name == "_oracle_says_pass"):
            continue
        found = True
        # The predicate must reference GRADER_TYPES by name in a membership test.
        references_grader_types = False
        for inner in ast.walk(node):
            if isinstance(inner, ast.Compare):
                for comparator in inner.comparators:
                    if (isinstance(comparator, ast.Name) and comparator.id == "GRADER_TYPES") or \
                       (isinstance(comparator, ast.Attribute) and comparator.attr == "GRADER_TYPES"):
                        references_grader_types = True
        assert references_grader_types, (
            f"_oracle_says_pass does not reference GRADER_TYPES structurally: "
            f"{ast.unparse(node)}"
        )
        # No hand-typed grader type literals allowed.
        literals = {n.value for n in ast.walk(node)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        assert not (literals & set(bench_tasks.GRADER_TYPES)), (
            f"the predicate names grader types by hand: {sorted(literals & set(bench_tasks.GRADER_TYPES))}"
        )
        return
    assert found, "_oracle_says_pass is gone from benchmarks.py"


def test_a_real_command_contract_oracle_is_counted_through_that_branch(tmp_path: Path) -> None:
    """The producer, not my dict: a passing command contract has no case_count."""
    graded = bench_tasks.grade_command_contract(
        {"grader": {"type": "command_contract", "command": '{python} -c "print(1)"'}},
        tmp_path, grader_dir=tmp_path / "graders",
    )
    assert graded["passed"] is True, graded
    assert "case_count" not in graded, graded
    oracle = {k: v for k, v in graded.items() if k != "grader_type"}
    metrics = _report([_capped("cmd", oracle, **{"grader_type": graded["grader_type"]})])["metrics"]
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
    # M8-T93: the other half of the rule has to be readable too, or a reader who sees a
    # command oracle not counted wonders whether the metric is broken.
    assert "no known grader" in text, text


# --- M8-T118: review_rounds 印法 ----------------------------------------------
#
# The rounds live in the JSON row (bounded: 8 rounds, 200 chars each); markdown
# carries only the count. A capped run's post-mortem is visible in the table
# without exploding its four columns, and the full rationale stays one
# `results.json` lookup away.


def test_a_row_with_review_rounds_marks_its_count_in_the_table() -> None:
    row = _capped("t", {"passed": True}, grader_type="command_contract")
    row["review_rounds"] = [{"code": "completion_capped"}, {"code": "completion_capped"}]
    text = benchmarks.markdown_report(_report([row]))  # type: ignore[arg-type]
    assert "[2 review rounds]" in text, text


def test_a_single_review_round_reads_singular() -> None:
    row = _capped("t", {"passed": True}, grader_type="command_contract")
    row["review_rounds"] = [{"code": "completion_capped"}]
    text = benchmarks.markdown_report(_report([row]))  # type: ignore[arg-type]
    assert "[1 review round]" in text, text


def test_a_row_without_review_rounds_prints_no_marker() -> None:
    text = benchmarks.markdown_report(_report([_capped("t", {"passed": True})]))  # type: ignore[arg-type]
    assert "review round" not in text, text
    junk = _capped("t", {"passed": True})
    junk["review_rounds"] = 3  # not the produced shape: dropped, not printed
    text = benchmarks.markdown_report(_report([junk]))  # type: ignore[arg-type]
    assert "review round" not in text, text
