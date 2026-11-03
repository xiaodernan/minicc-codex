"""M8-T541 — `grading_coverage` 一个键两种量，报告现在说它报的是哪一种

改前在带上的 v2 套件（24 条任务，24 条都声明了评分器）实测：

| 调用 | `executed_count` | `grading_coverage` | `gradable_task_count` |
| --- | ---: | ---: | ---: |
| `--suite v2`（没有 `--run`，路线图 M4 的验收调用） | 0 | 1.0 | 24 |
| 同一个套件的任务定义 + 三行已完成（两行有判决、一行不声明 grader） | 3 | 0.6667 | 2 |

同一个键，两个不同的量：第一行是「任务定义里声明了评分器的比例」，第二行才是
`docs/BENCHMARK_EVALUATION.md` 写的那句「已运行样本中具备评分结果的比例」。报告里
没有任何一处说读者拿到的是哪一种，而 `bench_compare` 把它们并排印在同一行并按变体侧
判定门槛——实测把上面第一行那份报告拿去做 `--gate grading_coverage>=0.9`（夜间门自己
的那条下限）返回 **通过 rc=0**：一条样本都没运行的报告满足了为运行写下的覆盖率下限。
`build_report` 的 notes 里那句「每条执行过的行落进三种判决之一」在第一种报告上也没有
分母可对（24 + 0 + 0 对 `executed_count = 0`）。

口径由挑选分子的那**一个分支**给出，所以它不可能和旁边的数字不一致；本文件的腿三就是
这条不变式，腿四走的是路线图记录的那次真实调用。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from minicc import bench_tasks
from minicc.bench_compare import GATE_FLOORS, compare_reports, evaluate_gates, main, render_delta_table
from minicc.benchmarks import build_report, main as report_main, markdown_report

CI_FILE = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


def _tasks():
    return bench_tasks.v2_tasks()


def _declared(tasks):
    return [t for t in tasks if isinstance(t.get("grader"), dict) or t.get("verify_command")]


def _row(task, status, passed):
    return {"task_id": str(task["id"]), "category": str(task.get("category") or "c"),
            "status": status, "passed": passed, "latency_ms": 10, "cost_usd": 0.01}


def _executed_report(tasks):
    """Three executed rows on the shipped suite: two judged, one declaring nothing."""
    ungraded = dict(tasks[-1])
    ungraded["grader"] = None
    ungraded.pop("verify_command", None)
    tasks = [ungraded if t is tasks[-1] else t for t in tasks]
    judged = [t for t in _declared(tasks) if str(t["id"]) != str(ungraded["id"])][:2]
    assert len(judged) == 2, judged
    return build_report(tasks, [
        _row(judged[0], "completed", True),
        _row(judged[1], "completed", False),
        _row(ungraded, "completed", None),
    ])


def test_the_declaration_only_report_says_its_coverage_is_declared() -> None:
    """The number 1.0 with zero executed rows is a statement about the suite."""
    tasks = _tasks()
    report = build_report(tasks, [])
    metrics = report["metrics"]
    assert report["executed_count"] == 0
    assert metrics["grading_coverage"] == 1.0, metrics
    assert metrics["grading_coverage_basis"] == "declared", metrics
    # gradable_task_count follows the same basis: on a report that ran nothing it is
    # the declared count, derived here from the task list rather than pinned to 24.
    assert metrics["gradable_task_count"] == len(_declared(tasks)) == report["fixture_count"]


def test_a_run_report_says_its_coverage_is_executed() -> None:
    report = _executed_report(_tasks())
    metrics = report["metrics"]
    assert report["executed_count"] == 3
    assert metrics["grading_coverage"] == 0.6667, metrics
    assert metrics["grading_coverage_basis"] == "executed", metrics
    assert metrics["gradable_task_count"] == 2


def test_the_basis_and_the_number_always_come_from_the_same_denominator() -> None:
    """The invariant that makes the label worth printing.

    ``grading_coverage`` is ``gradable_task_count`` over the denominator its own
    basis names - ``executed_count`` on the executed basis, ``fixture_count`` on the
    declared one. A branch that moves the number without moving the label, or that
    takes the count from the other side, breaks this on at least one shape.
    """
    tasks = _tasks()
    shapes = [
        build_report([], []),
        build_report(tasks, []),
        build_report(tasks, [_row(tasks[0], "not_run", None)]),
        _executed_report(tasks),
        build_report(tasks, [_row(t, "completed", True) for t in _declared(tasks)[:2]]),
    ]
    for report in shapes:
        metrics = report["metrics"]
        basis = metrics["grading_coverage_basis"]
        coverage = metrics["grading_coverage"]
        count = metrics["gradable_task_count"]
        if basis is None:
            assert coverage is None and report["fixture_count"] == 0 and report["executed_count"] == 0
            continue
        denominator = report["executed_count"] if basis == "executed" else report["fixture_count"]
        assert denominator > 0, (basis, report)
        assert coverage == round(count / denominator, 4), (basis, metrics, report["executed_count"])
    # exactly two spellings, and no shape invents a third
    assert {r["metrics"]["grading_coverage_basis"] for r in shapes} <= {None, "declared", "executed"}


def test_the_documented_no_run_invocation_publishes_the_declared_basis(tmp_path) -> None:
    """The shipped seam: the invocation the roadmap's M4 acceptance runs.

    ``--suite v2`` without ``--run`` is how a reader gets a coverage number before
    spending any model call, so the report it writes has to say which quantity it is.
    """
    out = tmp_path / "report.json"
    assert report_main(["--suite", "v2", "--json-out", str(out)]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["executed_count"] == 0
    assert report["metrics"]["grading_coverage_basis"] == "declared", report["metrics"]
    lines = markdown_report(report).splitlines()
    row = next(k for k, ln in enumerate(lines) if ln.startswith("| grading_coverage |"))
    assert lines[row] == "| grading_coverage | 1.0 |", lines[row]
    # the label belongs *beside* the number: the printed order comes from a
    # hand-declared reading list, and a key missing from it lands at the bottom of
    # the table (sorted), where it explains nothing to the reader of that row.
    assert lines[row + 1] == "| grading_coverage_basis | declared |", lines[row:row + 2]


def test_the_comparator_refuses_a_pair_that_states_two_different_bases(tmp_path) -> None:
    """A declared number beside an executed one is not a coverage comparison.

    Before this batch the same pair printed
    ``| grading_coverage | 1 | 0.6667 | — |`` with no label and returned **rc=0**
    against ``--gate grading_coverage>=0.5``; the nightly's own floor (0.9) was met
    by a report that ran nothing.
    """
    skeleton = build_report(_tasks(), [])
    executed = _executed_report(_tasks())
    for label, base, var in (("declared→executed", skeleton, executed),
                             ("executed→declared", executed, skeleton)):
        comparison = compare_reports(base, var)
        assert comparison["grading_coverage_comparable"] is False, label
        notes = [n for n in comparison["notes"] if "口径" in n]
        assert len(notes) == 1, (label, comparison["notes"])
        assert "declared" in notes[0] and "executed" in notes[0], notes[0]
        gates = evaluate_gates(comparison, ["grading_coverage>=0.9"])
        assert gates[0]["actual"] is None and gates[0]["violated"], (label, gates)
        table = render_delta_table(comparison, gates)
        assert "(declared)" in table and "(executed)" in table, table

    base = tmp_path / "base.json"
    var = tmp_path / "var.json"
    base.write_text(json.dumps(skeleton), encoding="utf-8")
    var.write_text(json.dumps(executed), encoding="utf-8")
    assert main(["--baseline", str(base), "--variant", str(var),
                 "--gate", "grading_coverage>=0.9"]) == 1


def test_a_same_basis_pair_is_still_gated_on_the_number() -> None:
    """Control: the refusal is about the pair's bases, not about declared reports.

    Both-declared is what the nightly self-compare of a no-run report would be; it
    stays judgeable, because the two sides are the same quantity. Both-executed must
    still fail on 0.6667 < 0.9 rather than be excused.
    """
    skeleton = build_report(_tasks(), [])
    executed = _executed_report(_tasks())
    declared_pair = compare_reports(skeleton, skeleton)
    assert declared_pair["grading_coverage_comparable"] is True
    assert not [n for n in declared_pair["notes"] if "口径" in n]
    assert evaluate_gates(declared_pair, ["grading_coverage>=0.9"])[0]["actual"] == 1.0
    executed_pair = compare_reports(executed, executed)
    assert executed_pair["grading_coverage_comparable"] is True
    gate = evaluate_gates(executed_pair, ["grading_coverage>=0.9"])[0]
    assert gate["actual"] == 0.6667 and gate["violated"], gate


def test_a_report_predating_the_key_is_compared_as_unknown() -> None:
    """A basis nobody stated is not a basis mismatch.

    Same decision M8-T159 made for ``suite_version``: an absent identity reads as
    ``unknown`` and the comparison proceeds, because refusing here would red every
    legitimate old-vs-old run for a reason the reports never claimed to settle.
    """
    executed = _executed_report(_tasks())
    # The subject of "predating the key" must exist first: this leg builds its old
    # report by removing the key from a new one, so a product that never wrote the
    # key would red here as a KeyError instead of as the claim it is testing.
    assert "grading_coverage_basis" in executed["metrics"], executed["metrics"]
    old = json.loads(json.dumps(executed))
    old["metrics"].pop("grading_coverage_basis")
    comparison = compare_reports(old, executed)
    assert comparison["grading_coverage_comparable"] is True
    assert not [n for n in comparison["notes"] if "口径" in n]
    assert comparison["baseline"]["grading_coverage_basis"] is None
    assert "(unknown)" in render_delta_table(comparison)


def test_the_shipped_floor_names_the_basis_it_is_written_for() -> None:
    """``nightly >=0.9`` is a claim about one of the two quantities.

    The number stays reconciled with the workflow file (that door lives in
    ``test_the_nightly_floor_values_have_a_reader.py``); this leg charges the half
    this batch adds - the floor row has to say which basis it thresholds, and the
    number it names has to be the one ci.yml actually pins.
    """
    floor = GATE_FLOORS["grading_coverage"]
    assert floor.startswith("nightly >=0.9"), floor
    assert "executed basis" in floor, floor
    assert "different bases" in floor, floor
    workflow = re.search(r"--gate grading_coverage>=([0-9.]+)", CI_FILE.read_text(encoding="utf-8"))
    assert workflow, "the nightly no longer pins a grading_coverage floor"
    assert floor.startswith(f"nightly >={workflow.group(1)}"), (floor, workflow.group(1))


def test_the_notes_name_the_key_and_the_basis_it_labels() -> None:
    """The report's own prose carries the reading rule, not only the new key."""
    report = build_report(_tasks(), [])
    notes = [n for n in report["notes"] if "grading_coverage_basis" in n]
    assert len(notes) == 1, report["notes"]
    note = notes[0]
    assert "gradable_task_count" in note, note
    assert "executed_count is then 0" in note, note
    assert "'declared'" in note and "'executed'" in note, note


def test_the_new_key_is_a_metric_and_not_a_gate_vocabulary_entry() -> None:
    """The basis label must not quietly become thresholdable.

    ``GATE_METRICS`` is the whole vocabulary a ``--gate`` accepts and
    ``GATE_FLOORS`` must carry exactly one row per entry (``test_ci_hygiene`` holds
    that). A basis is not a measurement, so it belongs to neither table - and an
    attempt to gate on it has to be a usage error rather than a silent None.
    """
    from minicc.bench_compare import GATE_FLOORS as FLOORS, GATE_METRICS as METRICS

    assert set(FLOORS) == set(METRICS)
    assert "grading_coverage_basis" not in METRICS
    with pytest.raises(ValueError, match="grading_coverage_basis"):
        from minicc.bench_compare import parse_gate

        parse_gate("grading_coverage_basis>=1")
