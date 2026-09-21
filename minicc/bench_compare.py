"""A/B comparator for two minicc evaluation reports.

M4 only ever produced absolute metrics, which cannot answer the one question a
36-week iteration loop lives on: *did this change actually help?* This module
aligns two ``build_report`` JSON outputs task-by-task and reports the movement:

* pass@1 delta with a Wilson 95% score interval (and a Newcombe interval for
  the difference of the two proportions),
* per-success cost delta with a paired bootstrap interval,
* latency p50/p95 deltas,
* a per-category breakdown.

``--gate`` turns the comparison into a pass/fail check (exit 1 on any
violation) so a regression cannot merge silently. ``--repeat N`` declares how
many independent draws back each report; per the roadmap pass@k is only claimed
when N >= 10 *and* the reports actually carry per-draw outcomes.

The comparator never fabricates a conclusion: an unavailable metric yields a
``None`` delta and a note, never a zero.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Any, Sequence

from .cli_io import cli_out

# scipy.stats.norm.ppf(0.975) — the two-sided 95% normal quantile.
Z95 = 1.959963984540054
MIN_REPEATS_FOR_PASSK = 10
GATE_METRICS = frozenset({
    "pass_at_1",
    "cost_per_success_usd",
    "latency_p95_ms",
    "grading_coverage",
})


def _is_number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def wilson_ci(successes: int, trials: int, *, z: float = Z95) -> tuple[float, float] | None:
    """Wilson score interval for a binomial proportion; ``None`` when trials==0.

    Preferred over the normal approximation because it stays inside [0, 1] and
    behaves correctly for small samples and extreme proportions (0/N, N/N),
    which is exactly the regime a 12-task fixture comparison lives in.
    """
    if trials <= 0:
        return None
    if successes < 0 or successes > trials:
        raise ValueError(f"successes 必须落在 [0, trials]: {successes}/{trials}")
    phat = successes / trials
    z2 = z * z
    denom = 1.0 + z2 / trials
    center = (phat + z2 / (2.0 * trials)) / denom
    margin = (z * math.sqrt(phat * (1.0 - phat) / trials + z2 / (4.0 * trials * trials))) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def newcombe_delta_ci(
    base_succ: int, base_trials: int, var_succ: int, var_trials: int, *, z: float = Z95
) -> tuple[float, float] | None:
    """Newcombe hybrid-score interval for ``p_variant - p_baseline``.

    Built from the two Wilson intervals; valid only when both sides have at
    least one trial.
    """
    lo1 = wilson_ci(base_succ, base_trials, z=z)
    lo2 = wilson_ci(var_succ, var_trials, z=z)
    if lo1 is None or lo2 is None:
        return None
    l1, u1 = lo1
    l2, u2 = lo2
    p1 = base_succ / base_trials
    p2 = var_succ / var_trials
    delta = p2 - p1
    lower = delta - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    upper = delta + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return (max(-1.0, lower), min(1.0, upper))


def _percentile(ordered: Sequence[float], ratio: float) -> float | None:
    """Linear-interpolation (R-7) quantile of an already-sorted sample."""
    if not ordered:
        return None
    values = list(ordered)
    position = (len(values) - 1) * max(0.0, min(1.0, ratio))
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def quantile(values: Sequence[float], ratio: float) -> float | None:
    finite = sorted(float(v) for v in values if _is_number(v))
    result = _percentile(finite, ratio)
    return None if result is None else round(result, 3)


def _normalize_rows(payload: object) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Accept either a build_report dict or a raw run_benchmark results list."""
    if isinstance(payload, dict):
        rows = payload.get("results")
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    elif isinstance(payload, list):
        rows, metrics = payload, {}
    else:
        raise ValueError("报告 JSON 必须是 build_report 对象或 results 数组")
    if not isinstance(rows, list):
        raise ValueError("报告缺少 results 数组")
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("task_id"), str):
            continue
        normalized.append({
            "task_id": row["task_id"],
            "category": str(row.get("category") or "uncategorized"),
            "status": row.get("status"),
            # None means "no automated grader" — it must never count as a fail.
            "passed": row.get("passed"),
            "latency_ms": row.get("latency_ms") if _is_number(row.get("latency_ms")) else None,
            "cost_usd": row.get("cost_usd") if _is_number(row.get("cost_usd")) else None,
            "draws": row.get("draws") if isinstance(row.get("draws"), list) else None,
        })
    return normalized, metrics


def _index(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        out[row["task_id"]] = row
    return out


def _pass_stats(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    gradable = [row for row in rows if row["passed"] is not None]
    passed = [row for row in gradable if row["passed"] is True]
    rate = round(len(passed) / len(gradable), 4) if gradable else None
    return {
        "task_count": len(rows),
        "gradable": len(gradable),
        "passed": len(passed),
        "pass_at_1": rate,
        "pass_at_1_ci": wilson_ci(len(passed), len(gradable)),
    }


def _cost_per_success(rows: Sequence[dict[str, Any]]) -> float | None:
    passed = [row for row in rows if row["passed"] is True]
    if not passed:
        return None
    costs = [row["cost_usd"] for row in rows if row["cost_usd"] is not None]
    if not costs or len(costs) != sum(1 for row in rows if row["status"] != "not_run"):
        # Mirror build_report: per-success cost stays null unless every executed
        # task carries a price, so we never report a misleadingly cheap number.
        return None
    return round(sum(costs) / len(passed), 6)


def _latencies(rows: Sequence[dict[str, Any]]) -> dict[str, float | None]:
    values = [row["latency_ms"] for row in rows if row["latency_ms"] is not None]
    return {"p50": quantile(values, 0.5), "p95": quantile(values, 0.95)}


def _bootstrap_cost_delta_ci(
    base_rows: list[dict[str, Any]],
    var_rows: list[dict[str, Any]],
    ids: Sequence[str],
    *,
    iterations: int,
    seed: int,
) -> tuple[float, float] | None:
    """Paired bootstrap over aligned task ids for the cost-per-success delta.

    Resamples the *task ids* (not the rows) with replacement so each draw keeps
    the baseline/variant pairing, recomputes both per-success costs, and keeps
    the 2.5/97.5 percentiles of the delta distribution. Returns None when fewer
    than two resamples produce a defined delta on both sides.
    """
    base_by_id = {row["task_id"]: row for row in base_rows}
    var_by_id = {row["task_id"]: row for row in var_rows}
    ids = [tid for tid in ids if tid in base_by_id and tid in var_by_id]
    if not ids:
        return None
    rng = random.Random(seed)
    deltas: list[float] = []
    n = len(ids)
    for _ in range(max(0, int(iterations))):
        sample = [ids[rng.randrange(n)] for _ in range(n)]
        base_sample = [base_by_id[tid] for tid in sample]
        var_sample = [var_by_id[tid] for tid in sample]
        base_cost = _cost_per_success(base_sample)
        var_cost = _cost_per_success(var_sample)
        if base_cost is not None and var_cost is not None:
            deltas.append(var_cost - base_cost)
    if len(deltas) < 2:
        return None
    deltas.sort()
    return (round(_percentile(deltas, 0.025), 6), round(_percentile(deltas, 0.975), 6))


def _pass_at_k(rows: Sequence[dict[str, Any]], k: int) -> float | None:
    """pass@k from per-draw outcomes; None unless every gradable row has >= k draws."""
    gradable = [row for row in rows if row["passed"] is not None and row["draws"]]
    if not gradable:
        return None
    for row in gradable:
        if len(row["draws"]) < k:
            return None
    # Unbiased pass@k estimator: 1 - C(n-c, k) / C(n, k).
    total = 0.0
    for row in gradable:
        draws = row["draws"]
        n = len(draws)
        c = sum(1 for draw in draws if draw is True)
        if n - c < k:
            total += 1.0
            continue
        # log-space to avoid overflow on large n.
        log_ratio = sum(math.log(n - c - i) - math.log(n - i) for i in range(k))
        total += 1.0 - math.exp(log_ratio)
    return round(total / len(gradable), 4)


def compare_reports(
    baseline: object,
    variant: object,
    *,
    repeat: int = 1,
    bootstrap_iterations: int = 2000,
    seed: int = 20260921,
) -> dict[str, Any]:
    """Align two reports task-by-task and compute the movement between them."""
    base_rows, base_metrics = _normalize_rows(baseline)
    var_rows, var_metrics = _normalize_rows(variant)
    base_by_id = _index(base_rows)
    var_by_id = _index(var_rows)
    shared = [tid for tid in base_by_id if tid in var_by_id]
    base_only = sorted(set(base_by_id) - set(var_by_id))
    var_only = sorted(set(var_by_id) - set(base_by_id))

    base_aligned = [base_by_id[tid] for tid in shared]
    var_aligned = [var_by_id[tid] for tid in shared]

    base_stats = _pass_stats(base_aligned)
    var_stats = _pass_stats(var_aligned)

    notes: list[str] = []
    if base_only or var_only:
        notes.append(
            f"任务集不完全对齐：baseline 独有 {len(base_only)} 条、variant 独有 "
            f"{len(var_only)} 条；delta 仅在 {len(shared)} 条共有任务上计算。"
        )

    pass_delta = (
        round(var_stats["pass_at_1"] - base_stats["pass_at_1"], 4)
        if base_stats["pass_at_1"] is not None and var_stats["pass_at_1"] is not None
        else None
    )
    pass_delta_ci = newcombe_delta_ci(
        base_stats["passed"], base_stats["gradable"],
        var_stats["passed"], var_stats["gradable"],
    )
    if pass_delta is None:
        notes.append("至少一侧没有可评分任务，pass@1 差值不可计算（None，而非 0）。")

    base_cost = _cost_per_success(base_aligned)
    var_cost = _cost_per_success(var_aligned)
    cost_delta = (
        round(var_cost - base_cost, 6) if base_cost is not None and var_cost is not None else None
    )
    cost_delta_ci = (
        _bootstrap_cost_delta_ci(
            base_aligned, var_aligned, shared,
            iterations=bootstrap_iterations, seed=seed,
        )
        if cost_delta is not None else None
    )
    if cost_delta is None:
        notes.append("成本数据缺失（无 passed 任务或价格不全），cost 差值不可计算。")

    base_lat = _latencies(base_aligned)
    var_lat = _latencies(var_aligned)
    lat_p50_delta = (
        round(var_lat["p50"] - base_lat["p50"], 3)
        if base_lat["p50"] is not None and var_lat["p50"] is not None else None
    )
    lat_p95_delta = (
        round(var_lat["p95"] - base_lat["p95"], 3)
        if base_lat["p95"] is not None and var_lat["p95"] is not None else None
    )

    categories: dict[str, Any] = {}
    for tid in shared:
        category = var_by_id[tid]["category"] or base_by_id[tid]["category"]
        bucket = categories.setdefault(category, {"base": [], "var": []})
        bucket["base"].append(base_by_id[tid])
        bucket["var"].append(var_by_id[tid])
    category_breakdown: dict[str, Any] = {}
    for category, bucket in sorted(categories.items()):
        bs = _pass_stats(bucket["base"])
        vs = _pass_stats(bucket["var"])
        category_breakdown[category] = {
            "task_count": len(bucket["var"]),
            "baseline_pass_at_1": bs["pass_at_1"],
            "variant_pass_at_1": vs["pass_at_1"],
            "delta": (
                round(vs["pass_at_1"] - bs["pass_at_1"], 4)
                if bs["pass_at_1"] is not None and vs["pass_at_1"] is not None else None
            ),
        }

    # pass@k: only claim it with >= 10 declared repeats AND real per-draw data.
    pass_at_k: dict[str, Any] | None = None
    k = int(repeat)
    if k < MIN_REPEATS_FOR_PASSK:
        notes.append(
            f"--repeat={k} < {MIN_REPEATS_FOR_PASSK}：按路线图不给出 pass@k 结论，"
            "仅报告 pass@1。"
        )
    else:
        base_pk = _pass_at_k(base_aligned, k)
        var_pk = _pass_at_k(var_aligned, k)
        if base_pk is None or var_pk is None:
            notes.append(
                f"--repeat={k} 但报告未携带每任务 ≥{k} 次抽样结果（draws），"
                "无法计算 pass@k。"
            )
        else:
            pass_at_k = {"k": k, "baseline": base_pk, "variant": var_pk}

    return {
        "schema_version": 1,
        "aligned_task_count": len(shared),
        "baseline_only_task_ids": base_only,
        "variant_only_task_ids": var_only,
        "baseline": {
            **base_stats,
            "cost_per_success_usd": base_cost,
            "latency_p50_ms": base_lat["p50"],
            "latency_p95_ms": base_lat["p95"],
            "grading_coverage": base_metrics.get("grading_coverage"),
        },
        "variant": {
            **var_stats,
            "cost_per_success_usd": var_cost,
            "latency_p50_ms": var_lat["p50"],
            "latency_p95_ms": var_lat["p95"],
            "grading_coverage": var_metrics.get("grading_coverage"),
        },
        "pass_at_1_delta": pass_delta,
        "pass_at_1_delta_ci": pass_delta_ci,
        "cost_per_success_delta": cost_delta,
        "cost_per_success_delta_ci": cost_delta_ci,
        "latency_p50_delta_ms": lat_p50_delta,
        "latency_p95_delta_ms": lat_p95_delta,
        "categories": category_breakdown,
        "pass_at_k": pass_at_k,
        "repeat": k,
        "notes": notes,
    }


def parse_gate(spec: str) -> dict[str, Any]:
    """Parse ``metric>=value`` / ``metric<=value`` (also ``>``/``<``)."""
    text = str(spec).strip()
    for op in (">=", "<=", ">", "<"):
        if op in text:
            metric, _, raw_value = text.partition(op)
            metric = metric.strip()
            if metric not in GATE_METRICS:
                raise ValueError(f"未知 gate 指标: {metric}（支持 {sorted(GATE_METRICS)}）")
            try:
                threshold = float(raw_value.strip())
            except ValueError as exc:
                raise ValueError(f"gate 阈值非法: {spec}") from exc
            if not math.isfinite(threshold):
                raise ValueError(f"gate 阈值必须有限: {spec}")
            return {"metric": metric, "op": op, "threshold": threshold, "spec": text}
    raise ValueError(f"gate 缺少比较符（>=, <=, >, <）: {spec}")


def _gate_actual(variant: dict[str, Any], metric: str) -> float | None:
    value = variant.get(metric)
    return value if _is_number(value) else None


def _gate_holds(actual: float | None, op: str, threshold: float) -> bool:
    if actual is None:
        return False  # fail closed: an unavailable metric cannot satisfy a gate.
    if op == ">=":
        return actual >= threshold
    if op == "<=":
        return actual <= threshold
    if op == ">":
        return actual > threshold
    return actual < threshold


def evaluate_gates(comparison: dict[str, Any], gates: Sequence[str]) -> list[dict[str, Any]]:
    """Evaluate every gate against the *variant* metrics; return all results."""
    variant = comparison.get("variant", {})
    results: list[dict[str, Any]] = []
    for spec in gates:
        gate = parse_gate(spec)
        actual = _gate_actual(variant, gate["metric"])
        holds = _gate_holds(actual, gate["op"], gate["threshold"])
        results.append({**gate, "actual": actual, "violated": not holds})
    return results


def _fmt(value: object, digits: int = 4) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}".rstrip("0").rstrip(".") if isinstance(value, float) else str(value)
    return str(value)


def _fmt_ci(ci: object, digits: int = 4) -> str:
    if not isinstance(ci, (list, tuple)) or len(ci) != 2:
        return "N/A"
    return f"[{_fmt(ci[0], digits)}, {_fmt(ci[1], digits)}]"


def render_delta_table(comparison: dict[str, Any], gates: Sequence[dict[str, Any]] = ()) -> str:
    base = comparison["baseline"]
    var = comparison["variant"]
    lines = [
        "# minicc A/B 对比",
        "",
        f"对齐任务数: {comparison['aligned_task_count']} | repeat={comparison.get('repeat', 1)}",
        "",
        "| 指标 | baseline | variant | 差值 (var-base) |",
        "| --- | ---: | ---: | ---: |",
        f"| pass@1 | {_fmt(base['pass_at_1'])} | {_fmt(var['pass_at_1'])} | {_fmt(comparison['pass_at_1_delta'])} |",
        f"| pass@1 Wilson 95% CI | {_fmt_ci(base['pass_at_1_ci'])} | {_fmt_ci(var['pass_at_1_ci'])} | — |",
        f"| pass@1 差值 Newcombe 95% CI | — | — | {_fmt_ci(comparison['pass_at_1_delta_ci'])} |",
        f"| cost_per_success_usd | {_fmt(base['cost_per_success_usd'], 6)} | {_fmt(var['cost_per_success_usd'], 6)} | {_fmt(comparison['cost_per_success_delta'], 6)} |",
        f"| cost 差值 bootstrap 95% CI | — | — | {_fmt_ci(comparison['cost_per_success_delta_ci'], 6)} |",
        f"| latency_p50_ms | {_fmt(base['latency_p50_ms'], 1)} | {_fmt(var['latency_p50_ms'], 1)} | {_fmt(comparison['latency_p50_delta_ms'], 1)} |",
        f"| latency_p95_ms | {_fmt(base['latency_p95_ms'], 1)} | {_fmt(var['latency_p95_ms'], 1)} | {_fmt(comparison['latency_p95_delta_ms'], 1)} |",
        f"| grading_coverage | {_fmt(base['grading_coverage'])} | {_fmt(var['grading_coverage'])} | — |",
    ]
    if comparison.get("categories"):
        lines.extend(["", "| Category | 任务 | pass@1 base | pass@1 var | 差值 |", "| --- | ---: | ---: | ---: | ---: |"])
        for category, row in comparison["categories"].items():
            lines.append(
                f"| {category} | {row['task_count']} | {_fmt(row['baseline_pass_at_1'])} "
                f"| {_fmt(row['variant_pass_at_1'])} | {_fmt(row['delta'])} |"
            )
    pk = comparison.get("pass_at_k")
    if pk:
        lines.extend(["", f"pass@{pk['k']}: baseline={_fmt(pk['baseline'])} variant={_fmt(pk['variant'])}"])
    if gates:
        lines.extend(["", "| Gate | 阈值 | 实际 | 结论 |", "| --- | ---: | ---: | --- |"])
        for gate in gates:
            verdict = "违反" if gate["violated"] else "通过"
            lines.append(
                f"| {gate['metric']} | {gate['op']} {gate['threshold']:g} "
                f"| {_fmt(gate['actual'], 6)} | {verdict} |"
            )
    if comparison.get("notes"):
        lines.extend(["", *[f"- {note}" for note in comparison["notes"]]])
    lines.append("")
    return "\n".join(lines)


def render_junit(comparison: dict[str, Any], gates: Sequence[dict[str, Any]]) -> str:
    """Minimal JUnit XML: one testcase per gate, <failure> when violated."""
    def esc(text: str) -> str:
        return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace('"', "&quot;"))
    failures = sum(1 for gate in gates if gate["violated"])
    cases = [
        f'<testsuite name="minicc.bench_compare" tests="{len(gates)}" failures="{failures}">'
    ]
    for gate in gates:
        name = esc(f"{gate['metric']} {gate['op']} {gate['threshold']:g}")
        cases.append(f'  <testcase classname="gate" name="{name}">')
        if gate["violated"]:
            actual = "None" if gate["actual"] is None else f"{gate['actual']:g}"
            message = esc(f"gate 违反: {gate['spec']} 实际={actual}")
            cases.append(f'    <failure message="{message}">{message}</failure>')
        cases.append("  </testcase>")
    cases.append("</testsuite>")
    return "\n".join(cases) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="minicc.benchmarks compare",
        description="对比两次评测 run 的 JSON，输出 pass@1/cost/latency 的 delta 与置信区间",
    )
    parser.add_argument("--baseline", type=Path, required=True, help="基线报告 JSON")
    parser.add_argument("--variant", type=Path, required=True, help="改动后报告 JSON")
    parser.add_argument("--gate", action="append", default=[],
                        help="阈值门槛，如 pass_at_1>=0.8；可重复，违反则 exit 1")
    parser.add_argument("--repeat", type=int, default=1,
                        help="每份报告背后的独立抽样次数；<10 不给出 pass@k 结论")
    parser.add_argument("--bootstrap-iterations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260921)
    parser.add_argument("--json-out", type=Path, help="把对比结果写入 JSON")
    parser.add_argument("--junit-out", type=Path, help="把 gate 结果写入 JUnit XML")
    args = parser.parse_args(argv)

    if args.repeat < 1:
        parser.error("--repeat 必须 >= 1")
    if args.bootstrap_iterations < 0:
        parser.error("--bootstrap-iterations 不能为负")

    try:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        variant = json.loads(args.variant.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f"读取报告失败: {exc}")

    comparison = compare_reports(
        baseline, variant,
        repeat=args.repeat,
        bootstrap_iterations=args.bootstrap_iterations,
        seed=args.seed,
    )

    gates: list[dict[str, Any]] = []
    for spec in args.gate:
        try:
            parsed = parse_gate(spec)
        except ValueError as exc:
            parser.error(str(exc))
        actual = _gate_actual(comparison["variant"], parsed["metric"])
        gates.append({**parsed, "actual": actual,
                      "violated": not _gate_holds(actual, parsed["op"], parsed["threshold"])})
    comparison["gates"] = gates

    cli_out(render_delta_table(comparison, gates))

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if args.junit_out is not None:
        args.junit_out.parent.mkdir(parents=True, exist_ok=True)
        args.junit_out.write_text(render_junit(comparison, gates), encoding="utf-8")

    violated = [gate for gate in gates if gate["violated"]]
    if violated:
        cli_out(f"\n[GATE FAILED] {len(violated)} 个门槛被违反：")
        for gate in violated:
            actual = "None" if gate["actual"] is None else f"{gate['actual']:g}"
            cli_out(f"  - {gate['spec']} 实际={actual}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
