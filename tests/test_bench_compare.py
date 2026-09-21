"""M4-T6: A/B comparator and statistical gates.

Acceptance (roadmap line ~211): construct 12-task two-version results, assert
the CI matches a hand calculation, assert ``main()`` returns 1 when a gate is
violated, and verify the gate goes red on constructed data when the threshold is
set impossibly high. pass@k must stay unclaimed for ``--repeat < 10``.
"""

from __future__ import annotations

import json
import math

import pytest

from minicc import bench_compare
from minicc.bench_compare import (
    Z95,
    compare_reports,
    evaluate_gates,
    parse_gate,
    render_delta_table,
    render_junit,
    wilson_ci,
    newcombe_delta_ci,
    main,
)
from minicc.benchmarks import build_report


# --- independent reference implementations ("手算") -------------------------


def _ref_wilson(successes: int, trials: int, z: float = Z95) -> tuple[float, float]:
    phat = successes / trials
    z2 = z * z
    denom = 1 + z2 / trials
    center = (phat + z2 / (2 * trials)) / denom
    margin = z * math.sqrt(phat * (1 - phat) / trials + z2 / (4 * trials * trials)) / denom
    return (center - margin, center + margin)


def _ref_newcombe(b_succ, b_trials, v_succ, v_trials):
    l1, u1 = _ref_wilson(b_succ, b_trials)
    l2, u2 = _ref_wilson(v_succ, v_trials)
    p1 = b_succ / b_trials
    p2 = v_succ / v_trials
    delta = p2 - p1
    return (
        delta - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2),
        delta + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2),
    )


def _ref_quantile(values, ratio):
    ordered = sorted(values)
    pos = (len(ordered) - 1) * ratio
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


# --- fixture builders ------------------------------------------------------


def _tasks():
    cats = ["write"] * 6 + ["test-fix"] * 6
    return [{"id": f"t{i}", "category": cats[i]} for i in range(12)]


def _results(passed_flags, *, latency_unit=100.0, cost_unit=0.01):
    out = []
    for i, flag in enumerate(passed_flags):
        out.append({
            "task_id": f"t{i}",
            "status": "completed",
            "passed": bool(flag),
            "latency_ms": latency_unit * (i + 1),
            "cost_usd": cost_unit,
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        })
    return out


def _report(passed_flags, **kw):
    return build_report(_tasks(), _results(passed_flags, **kw))


# 6/12 baseline, 9/12 variant.
_BASE_FLAGS = [True, False] * 6  # 6 True
_VAR_FLAGS = [True] * 9 + [False] * 3  # 9 True, 3 False


# --- Wilson / Newcombe -----------------------------------------------------


def test_wilson_ci_matches_closed_form():
    lo, hi = wilson_ci(9, 12)
    rlo, rhi = _ref_wilson(9, 12)
    assert lo == pytest.approx(rlo, abs=1e-12)
    assert hi == pytest.approx(rhi, abs=1e-12)
    assert 0.0 <= lo < 0.75 < hi <= 1.0


def test_wilson_ci_edge_cases():
    assert wilson_ci(0, 0) is None
    lo, hi = wilson_ci(0, 5)
    assert lo == 0.0 and 0.0 < hi < 1.0
    lo, hi = wilson_ci(5, 5)
    assert 0.0 < lo < 1.0 and hi == 1.0
    with pytest.raises(ValueError):
        wilson_ci(6, 5)


def test_newcombe_delta_ci_matches_closed_form():
    ci = newcombe_delta_ci(6, 12, 9, 12)
    ref = _ref_newcombe(6, 12, 9, 12)
    assert ci[0] == pytest.approx(ref[0], abs=1e-12)
    assert ci[1] == pytest.approx(ref[1], abs=1e-12)
    assert newcombe_delta_ci(0, 0, 1, 2) is None


# --- compare_reports -------------------------------------------------------


def test_pass_at_1_delta_and_ci():
    cmp = compare_reports(_report(_BASE_FLAGS), _report(_VAR_FLAGS))
    assert cmp["aligned_task_count"] == 12
    assert cmp["baseline"]["pass_at_1"] == 0.5
    assert cmp["variant"]["pass_at_1"] == 0.75
    assert cmp["pass_at_1_delta"] == pytest.approx(0.25)
    # per-version Wilson intervals match the hand calculation
    blo, bhi = cmp["baseline"]["pass_at_1_ci"]
    rblo, rbhi = _ref_wilson(6, 12)
    assert (blo, bhi) == (pytest.approx(rblo, abs=1e-9), pytest.approx(rbhi, abs=1e-9))
    # delta interval matches Newcombe
    dlo, dhi = cmp["pass_at_1_delta_ci"]
    rdlo, rdhi = _ref_newcombe(6, 12, 9, 12)
    assert dlo == pytest.approx(rdlo, abs=1e-9)
    assert dhi == pytest.approx(rdhi, abs=1e-9)
    assert dlo < 0.25 < dhi


def test_cost_delta_and_bootstrap_ci():
    base = _report(_BASE_FLAGS, cost_unit=0.01)   # sum 0.12 / 6 passed = 0.02
    var = _report(_VAR_FLAGS, cost_unit=0.008)    # sum 0.096 / 9 passed
    cmp = compare_reports(base, var, bootstrap_iterations=500, seed=7)
    assert cmp["baseline"]["cost_per_success_usd"] == pytest.approx(0.02, abs=1e-6)
    expected_var = round(0.008 * 12 / 9, 6)
    assert cmp["variant"]["cost_per_success_usd"] == pytest.approx(expected_var, abs=1e-6)
    assert cmp["cost_per_success_delta"] == pytest.approx(expected_var - 0.02, abs=1e-6)
    ci = cmp["cost_per_success_delta_ci"]
    assert ci is not None and ci[0] <= ci[1]
    assert all(math.isfinite(x) for x in ci)


def test_latency_p50_p95_deltas():
    base = _report(_BASE_FLAGS, latency_unit=100.0)  # 100..1200
    var = _report(_VAR_FLAGS, latency_unit=80.0)     # 80..960
    cmp = compare_reports(base, var)
    values_b = [100.0 * (i + 1) for i in range(12)]
    values_v = [80.0 * (i + 1) for i in range(12)]
    assert cmp["baseline"]["latency_p50_ms"] == pytest.approx(_ref_quantile(values_b, 0.5), abs=1e-3)
    assert cmp["baseline"]["latency_p95_ms"] == pytest.approx(_ref_quantile(values_b, 0.95), abs=1e-3)
    assert cmp["latency_p50_delta_ms"] == pytest.approx(
        _ref_quantile(values_v, 0.5) - _ref_quantile(values_b, 0.5), abs=1e-3)
    assert cmp["latency_p95_delta_ms"] == pytest.approx(
        _ref_quantile(values_v, 0.95) - _ref_quantile(values_b, 0.95), abs=1e-3)
    assert cmp["latency_p95_delta_ms"] < 0  # variant is faster


def test_category_breakdown():
    cmp = compare_reports(_report(_BASE_FLAGS), _report(_VAR_FLAGS))
    cats = cmp["categories"]
    assert set(cats) == {"write", "test-fix"}
    assert cats["write"]["task_count"] == 6
    assert cats["test-fix"]["task_count"] == 6
    # every category delta is defined and equals var-base on that subset
    for row in cats.values():
        assert row["delta"] == pytest.approx(
            row["variant_pass_at_1"] - row["baseline_pass_at_1"], abs=1e-9)


def test_unaligned_tasks_reported_not_silently_dropped():
    base = _report(_BASE_FLAGS)
    var_report = _report(_VAR_FLAGS)
    # drop t11 from the variant so the task sets diverge
    var_report["results"] = [r for r in var_report["results"] if r["task_id"] != "t11"]
    cmp = compare_reports(base, var_report)
    assert cmp["aligned_task_count"] == 11
    assert cmp["variant_only_task_ids"] == []
    assert "t11" in cmp["baseline_only_task_ids"]
    assert any("对齐" in note for note in cmp["notes"])


def test_missing_grader_yields_none_delta_not_zero():
    base = build_report(_tasks(), [])  # nothing executed → no gradable rows
    var = _report(_VAR_FLAGS)
    cmp = compare_reports(base, var)
    assert cmp["pass_at_1_delta"] is None
    assert cmp["pass_at_1_delta_ci"] is None
    assert any("pass@1 差值不可计算" in note for note in cmp["notes"])


# --- pass@k gating ---------------------------------------------------------


def test_repeat_below_10_does_not_claim_pass_at_k():
    cmp = compare_reports(_report(_BASE_FLAGS), _report(_VAR_FLAGS), repeat=3)
    assert cmp["pass_at_k"] is None
    assert cmp["repeat"] == 3
    assert any("--repeat=3" in note and "pass@k" in note for note in cmp["notes"])


def test_repeat_10_without_draws_cannot_compute_pass_at_k():
    cmp = compare_reports(_report(_BASE_FLAGS), _report(_VAR_FLAGS), repeat=10)
    assert cmp["pass_at_k"] is None
    assert any("draws" in note for note in cmp["notes"])


def test_pass_at_k_computed_with_per_draw_outcomes():
    def _report_with_draws(draws_per_task):
        rows = []
        for i, draws in enumerate(draws_per_task):
            rows.append({
                "task_id": f"t{i}", "category": "write", "status": "completed",
                "passed": any(draws), "latency_ms": 100.0, "cost_usd": 0.01,
                "draws": draws,
            })
        return {"results": rows, "metrics": {}}
    # 12 draws each; n-c < k(=10) only when successes >= 3.
    base_draws = [[True] + [False] * 11 for _ in range(12)]   # c=1 → n-c=11>=10
    var_draws = [[True] * 5 + [False] * 7 for _ in range(12)]  # c=5 → n-c=7<10 → 1.0
    cmp = compare_reports(
        _report_with_draws(base_draws), _report_with_draws(var_draws), repeat=10)
    pk = cmp["pass_at_k"]
    assert pk is not None and pk["k"] == 10
    # baseline: 1 - C(11,10)/C(12,10) = 1 - 11/66
    expected_base = round(1 - (11 / 66), 4)
    assert pk["baseline"] == pytest.approx(expected_base, abs=1e-4)
    assert pk["variant"] == 1.0


# --- gates -----------------------------------------------------------------


def test_parse_gate_forms():
    assert parse_gate("pass_at_1>=0.8") == {
        "metric": "pass_at_1", "op": ">=", "threshold": 0.8, "spec": "pass_at_1>=0.8"}
    assert parse_gate(" cost_per_success_usd <= 0.05 ")["op"] == "<="
    assert parse_gate("latency_p95_ms>30000")["op"] == ">"
    with pytest.raises(ValueError):
        parse_gate("unknown_metric>=1")
    with pytest.raises(ValueError):
        parse_gate("pass_at_1 0.8")  # no comparator
    with pytest.raises(ValueError):
        parse_gate("pass_at_1>=abc")


def test_evaluate_gates_fail_closed_on_none():
    cmp = {"variant": {"pass_at_1": 0.75, "cost_per_success_usd": None}}
    results = evaluate_gates(cmp, ["cost_per_success_usd<=0.05"])
    assert results[0]["violated"] is True  # None cannot satisfy a gate
    results = evaluate_gates(cmp, ["pass_at_1>=0.5"])
    assert results[0]["violated"] is False


def _write_reports(tmp_path):
    base_path = tmp_path / "a.json"
    var_path = tmp_path / "b.json"
    base_path.write_text(json.dumps(_report(_BASE_FLAGS)), encoding="utf-8")
    var_path.write_text(json.dumps(_report(_VAR_FLAGS)), encoding="utf-8")
    return base_path, var_path


def test_main_gate_violation_returns_1(tmp_path, capsys):
    base_path, var_path = _write_reports(tmp_path)
    # variant pass@1 = 0.75; an impossible 0.9 threshold must go red.
    code = main(["--baseline", str(base_path), "--variant", str(var_path),
                 "--gate", "pass_at_1>=0.9"])
    assert code == 1
    out = capsys.readouterr().out
    assert "GATE FAILED" in out
    assert "pass@1" in out  # human-readable delta table printed


def test_main_gate_satisfied_returns_0(tmp_path, capsys):
    base_path, var_path = _write_reports(tmp_path)
    code = main(["--baseline", str(base_path), "--variant", str(var_path),
                 "--gate", "pass_at_1>=0.5"])
    assert code == 0
    assert "GATE FAILED" not in capsys.readouterr().out


def test_main_writes_json_and_junit(tmp_path):
    base_path, var_path = _write_reports(tmp_path)
    json_out = tmp_path / "cmp.json"
    junit_out = tmp_path / "cmp.xml"
    code = main(["--baseline", str(base_path), "--variant", str(var_path),
                 "--gate", "pass_at_1>=0.9",
                 "--json-out", str(json_out), "--junit-out", str(junit_out)])
    assert code == 1
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["variant"]["pass_at_1"] == 0.75
    assert payload["gates"][0]["violated"] is True
    xml = junit_out.read_text(encoding="utf-8")
    assert "<testsuite" in xml and "<failure" in xml


def test_main_rejects_bad_gate_spec(tmp_path):
    base_path, var_path = _write_reports(tmp_path)
    with pytest.raises(SystemExit):
        main(["--baseline", str(base_path), "--variant", str(var_path),
              "--gate", "bogus>=1"])


def test_main_rejects_repeat_below_one(tmp_path):
    base_path, var_path = _write_reports(tmp_path)
    with pytest.raises(SystemExit):
        main(["--baseline", str(base_path), "--variant", str(var_path), "--repeat", "0"])


def test_render_delta_table_is_human_readable():
    cmp = compare_reports(_report(_BASE_FLAGS), _report(_VAR_FLAGS))
    gates = evaluate_gates(cmp, ["pass_at_1>=0.5"])
    table = render_delta_table(cmp, gates)
    assert "pass@1" in table and "Wilson" in table and "bootstrap" in table
    assert "write" in table and "test-fix" in table
    assert "通过" in table


def test_render_junit_escapes_and_counts_failures():
    cmp = compare_reports(_report(_BASE_FLAGS), _report(_VAR_FLAGS))
    gates = evaluate_gates(cmp, ["pass_at_1>=0.9", "pass_at_1>=0.1"])
    xml = render_junit(cmp, gates)
    assert 'failures="1"' in xml
    assert xml.count("<testcase") == 2


def test_benchmarks_main_dispatches_compare_subcommand(tmp_path):
    from minicc.benchmarks import main as benchmarks_main
    base_path, var_path = _write_reports(tmp_path)
    # `python -m minicc.benchmarks compare --baseline a.json --variant b.json`
    code = benchmarks_main(["compare", "--baseline", str(base_path),
                            "--variant", str(var_path), "--gate", "pass_at_1>=0.9"])
    assert code == 1
    # without a gate the same subcommand passes
    assert benchmarks_main(["compare", "--baseline", str(base_path),
                            "--variant", str(var_path)]) == 0

