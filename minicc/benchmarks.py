"""Offline, reproducible benchmark reporting for the local agent harness.

Fixtures are intentionally declarative.  Running this module never calls a
model, never fabricates token or price data, and can be supplied with recorded
results from a controlled evaluation run later.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any


DEFAULT_FIXTURES = Path(__file__).resolve().parent.parent / "benchmarks" / "tasks.json"


def load_tasks(path: Path = DEFAULT_FIXTURES) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or len(raw) != 30:
        raise ValueError("评测任务集必须恰好包含 30 个任务")
    seen: set[str] = set()
    for task in raw:
        if not isinstance(task, dict) or not isinstance(task.get("id"), str) or not task["id"]:
            raise ValueError("每个评测任务必须包含非空 id")
        if task["id"] in seen:
            raise ValueError(f"评测任务 id 重复: {task['id']}")
        seen.add(task["id"])
    return raw


def _quantile(values: list[float], ratio: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int((len(ordered) - 1) * ratio))], 3)


def build_report(tasks: list[dict[str, Any]], results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    by_id = {str(item.get("task_id")): item for item in results or [] if isinstance(item, dict)}
    rows: list[dict[str, Any]] = []
    for task in tasks:
        recorded = by_id.get(task["id"], {})
        row = {
            "task_id": task["id"],
            "category": task.get("category", "uncategorized"),
            "status": recorded.get("status", "not_run"),
            "passed": bool(recorded.get("passed")) if recorded else None,
            "latency_ms": recorded.get("latency_ms"),
            "repair_attempts": recorded.get("repair_attempts"),
            "tool_calls": recorded.get("tool_calls"),
            "repeated_tool_calls": recorded.get("repeated_tool_calls"),
            "usage": recorded.get("usage") if isinstance(recorded.get("usage"), dict) else None,
            "cost_usd": recorded.get("cost_usd") if isinstance(recorded.get("cost_usd"), (int, float)) else None,
        }
        rows.append(row)
    completed = [row for row in rows if row["status"] != "not_run"]
    passed = [row for row in completed if row["passed"] is True]
    latencies = [float(row["latency_ms"]) for row in completed if isinstance(row["latency_ms"], (int, float))]
    repairs = [int(row["repair_attempts"]) for row in completed if isinstance(row["repair_attempts"], (int, float))]
    repeated = sum(int(row["repeated_tool_calls"] or 0) for row in completed if isinstance(row["repeated_tool_calls"], (int, float)))
    calls = sum(int(row["tool_calls"] or 0) for row in completed if isinstance(row["tool_calls"], (int, float)))
    return {
        "schema_version": 1,
        "generated_at_epoch": time.time(),
        "fixture_count": len(tasks),
        "executed_count": len(completed),
        "results": rows,
        "metrics": {
            "pass_at_1": round(len(passed) / len(completed), 4) if completed else None,
            "latency_p50_ms": _quantile(latencies, 0.5),
            "latency_p95_ms": _quantile(latencies, 0.95),
            "mean_repair_attempts": round(statistics.mean(repairs), 3) if repairs else None,
            "tool_repeat_rate": round(repeated / calls, 4) if calls else None,
            "token_usage_available": sum(1 for row in completed if row["usage"] is not None),
            "cost_available": sum(1 for row in completed if row["cost_usd"] is not None),
        },
        "notes": [
            "not_run is not a pass or failure.",
            "Token and cost metrics remain null when the provider does not expose usage or pricing.",
        ],
    }


def markdown_report(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    def value(item: object) -> str:
        return "N/A" if item is None else str(item)
    lines = [
        "# minicc Evaluation Report",
        "",
        f"Fixtures: {report['fixture_count']} | Executed: {report['executed_count']}",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key in ("pass_at_1", "latency_p50_ms", "latency_p95_ms", "mean_repair_attempts", "tool_repeat_rate", "token_usage_available", "cost_available"):
        lines.append(f"| {key} | {value(metrics.get(key))} |")
    lines.extend(["", "| Task | Category | Status | Passed |", "| --- | --- | --- | --- |"])
    for row in report["results"]:
        lines.append(f"| {row['task_id']} | {row['category']} | {row['status']} | {value(row['passed'])} |")
    lines.extend(["", *[f"- {note}" for note in report["notes"]], ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成 minicc 离线评测报告")
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--results", type=Path)
    parser.add_argument("--json-out", type=Path, default=Path("output/evaluation.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("output/evaluation.md"))
    args = parser.parse_args(argv)
    tasks = load_tasks(args.fixtures)
    results = json.loads(args.results.read_text(encoding="utf-8")) if args.results else None
    if results is not None and not isinstance(results, list):
        parser.error("--results 必须是 JSON 数组")
    report = build_report(tasks, results)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown_out.write_text(markdown_report(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
