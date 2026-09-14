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
            # Preserve the None/False distinction: None means the task has no
            # automated grader (no verify_command), False means it failed one.
            "passed": (None if recorded.get("passed") is None else bool(recorded.get("passed"))) if recorded else None,
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
    gradable = [row for row in completed if row["passed"] is not None]
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
            # pass_at_1 counts only tasks with an automated grader; tasks
            # without verify_command report passed=None and must not dilute
            # the pass-rate denominator.
            "pass_at_1": round(len(passed) / len(gradable), 4) if gradable else None,
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
    parser.add_argument(
        "--run", action="store_true",
        help="实际执行评测任务（需要真实模型配置）；缺省时只生成报告骨架，不调用模型",
    )
    parser.add_argument("--max-tasks", type=int, help="配合 --run：只执行前 N 条任务")
    parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="配合 --run：评测工作区")
    args = parser.parse_args(argv)
    tasks = load_tasks(args.fixtures)
    results = None
    if args.run:
        results = run_benchmark(
            tasks,
            workspace=args.workspace.expanduser().resolve(),
            max_tasks=args.max_tasks,
            results_path=args.results,
        )
    elif args.results:
        results = json.loads(args.results.read_text(encoding="utf-8"))
    if results is not None and not isinstance(results, list):
        parser.error("--results 必须是 JSON 数组")
    report = build_report(tasks, results)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown_out.write_text(markdown_report(report), encoding="utf-8")
    return 0



# ---------------------------------------------------------------------------
# Live evaluation runner (Stage 4.4)
# ---------------------------------------------------------------------------


def run_benchmark(
    tasks: list[dict[str, Any]],
    *,
    workspace: Path,
    max_tasks: int | None = None,
    results_path: Path | None = None,
    resume: bool = True,
    task_timeout_seconds: float = 900.0,
) -> list[dict[str, Any]]:
    """Execute fixture tasks against the configured real model.

    Requires a live configuration (load_config must succeed with a real
    ``MINICC_API_KEY``); the runner never fabricates results. Each task runs
    through ``AgentService._chat_locked`` with writes disabled, then any
    ``verify_command`` (must be read-only) is executed to grade ``passed``.
    Results are flushed to ``results_path`` after every task so an interrupted
    run keeps its completed rows. With ``resume`` (default) previously
    completed task ids in ``results_path`` are skipped. Each task is bounded
    by ``task_timeout_seconds`` on the model phase and 300s on the verifier.
    """
    import subprocess as _subprocess
    import threading as _threading

    try:
        from .config import load_config
        from .web import AgentService
    except ImportError as exc:  # pragma: no cover - package layout guard
        raise RuntimeError(f"无法导入评测依赖: {exc}") from exc

    try:
        config = load_config()
    except Exception as exc:  # noqa: BLE001 - report config problems verbatim
        raise RuntimeError(f"评测需要真实模型配置（load_config 失败）: {exc}") from exc

    service = AgentService(workspace, config)
    results: list[dict[str, Any]] = []
    if resume and results_path is not None and results_path.is_file():
        try:
            prior = json.loads(results_path.read_text(encoding="utf-8"))
            if isinstance(prior, list):
                results = [item for item in prior if isinstance(item, dict) and item.get("task_id")]
        except (OSError, json.JSONDecodeError):
            results = []
    done_ids = {str(item.get("task_id")) for item in results if item.get("status") == "completed"}
    try:
        selected = tasks if max_tasks is None else tasks[: max(0, int(max_tasks))]
        for task in selected:
            if task["id"] in done_ids:
                continue
            started = time.monotonic()
            entry: dict[str, Any] = {"task_id": task["id"], "status": "failed", "passed": None}
            try:
                # The chat call is sync; bound it with a daemon worker so a
                # stalled model request cannot freeze the whole evaluation.
                # A daemon thread is abandoned on timeout instead of blocking
                # the run for a gateway that may hang indefinitely.
                outcome_box: dict[str, Any] = {}

                def _run_task() -> None:
                    try:
                        outcome_box["outcome"] = service._chat_locked(
                            {
                                "message": str(task.get("prompt") or ""),
                                "allow_changes": False,
                                "workspace_path": str(workspace),
                            },
                            workspace=workspace,
                        )
                    except BaseException as exc:  # noqa: BLE001 - forwarded below
                        outcome_box["error"] = exc

                worker = _threading.Thread(
                    target=_run_task, daemon=True, name=f"bench-{task['id']}"
                )
                worker.start()
                worker.join(timeout=max(60.0, float(task_timeout_seconds)))
                if worker.is_alive():
                    raise TimeoutError(f"task timeout > {int(task_timeout_seconds)}s")
                if "error" in outcome_box:
                    raise outcome_box["error"]
                outcome = outcome_box["outcome"]
            except TimeoutError:
                entry["status"] = "failed"
                entry["error"] = f"task timeout > {int(task_timeout_seconds)}s"
            except Exception as exc:  # noqa: BLE001 - one task must not kill the run
                entry["status"] = "failed"
                entry["error"] = f"{type(exc).__name__}: {exc}"[:200]
            else:
                entry["status"] = "failed" if outcome.get("error") else "completed"
                entry["turns"] = int(outcome.get("turns") or 0)
                entry["tool_calls"] = int(outcome.get("tool_calls_total") or 0)
                usage = outcome.get("tokens_used")
                if isinstance(usage, dict):
                    entry["usage"] = usage
                if outcome.get("error"):
                    entry["error"] = str(outcome["error"])[:200]
            entry["latency_ms"] = round((time.monotonic() - started) * 1000, 1)

            verify_command = task.get("verify_command")
            if verify_command:
                try:
                    completed = _subprocess.run(
                        str(verify_command), cwd=str(workspace), shell=True,
                        capture_output=True, text=True, timeout=300,
                    )
                    entry["passed"] = completed.returncode == 0
                except (_subprocess.TimeoutExpired, OSError):
                    entry["passed"] = False
            results.append(entry)
            if results_path is not None:
                results_path.parent.mkdir(parents=True, exist_ok=True)
                results_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        service.shutdown()
    return results


if __name__ == "__main__":
    raise SystemExit(main())
