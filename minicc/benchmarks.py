"""Offline, reproducible benchmark reporting for the local agent harness.

Fixtures are intentionally declarative.  Running this module never calls a
model, never fabricates token or price data, and can be supplied with recorded
results from a controlled evaluation run later.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
import time
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any, Sequence
from .behavior_bench import behavior_tasks, fixture_digest, grade_behavior, prepare_fixture
from . import bench_tasks
from .bench_tasks import grade_v2
from . import pricing
from .cli_io import cli_out


DEFAULT_FIXTURES = Path(__file__).resolve().parent.parent / "benchmarks" / "tasks.json"
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RETRIEVAL = REPO_ROOT / "benchmarks" / "retrieval-hitrate.json"
# M4-T7 decision rule: only introduce a local embedding model when the lexical
# baseline cannot reliably localize known answers. The roadmap fixes the bar at
# recall@5 < 0.6.
RETRIEVAL_RECALL_FLOOR = 0.6


def _measurement(value: object) -> bool:
    """Metrics accept actual finite, nonnegative measurements, not bools."""
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _write_results(path: Path, results: list[dict[str, Any]]) -> None:
    """Keep the previous complete checkpoint if a write is interrupted."""
    from .tools.registry import redact_text

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(redact_text(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False))[0] + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _resume_matches(item: dict[str, Any], task: dict[str, Any], metadata: dict[str, Any]) -> bool:
    recorded = item.get("metadata")
    return isinstance(recorded, dict) and all(recorded.get(key) == value for key, value in metadata.items()) and recorded.get("fixture_sha256") == fixture_digest(task)


def load_tasks(path: Path = DEFAULT_FIXTURES) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("评测任务集必须包含至少一个任务")
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
    # Linear interpolation (R-7); floor indexing reported the minimum as
    # p95 for a two-case smoke sample.
    position = (len(ordered) - 1) * max(0.0, min(1.0, ratio))
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower), 3)


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
            "passed": (None if recorded.get("passed") is None else recorded.get("status") == "completed" and recorded.get("passed") is True) if recorded else None,
            "latency_ms": recorded.get("latency_ms") if _measurement(recorded.get("latency_ms")) else None,
            "execution_latency_ms": recorded.get("execution_latency_ms"),
            "grading_latency_ms": recorded.get("grading_latency_ms"),
            "repair_attempts": recorded.get("repair_attempts"),
            "tool_calls": recorded.get("tool_calls"),
            "repeated_tool_calls": recorded.get("repeated_tool_calls"),
            "usage": recorded.get("usage") if isinstance(recorded.get("usage"), dict) else None,
            "cost_usd": recorded.get("cost_usd") if _measurement(recorded.get("cost_usd")) else None,
            "claimed_complete": recorded.get("claimed_complete", recorded.get("status") == "completed"),
            "grader_type": recorded.get("grader_type", "command" if task.get("verify_command") else "ungraded"),
            "metadata": recorded.get("metadata"),
        }
        rows.append(row)
    completed = [row for row in rows if row["status"] != "not_run"]
    passed = [row for row in completed if row["passed"] is True]
    gradable = [row for row in completed if row["passed"] is not None]
    latencies = [float(row["latency_ms"]) for row in completed if _measurement(row["latency_ms"])]
    repairs = [int(row["repair_attempts"]) for row in completed if _measurement(row["repair_attempts"])]
    repeated = sum(int(row["repeated_tool_calls"]) for row in completed if _measurement(row["repeated_tool_calls"]))
    calls = sum(int(row["tool_calls"]) for row in completed if _measurement(row["tool_calls"]))
    total_tokens_known = bool(completed) and all(_measurement((row["usage"] or {}).get("total_tokens")) for row in completed)
    total_cost_known = bool(completed) and all(row["cost_usd"] is not None for row in completed)
    # A suite is "fully gradable" by construction when every task declares a
    # grader or a verify_command. With no executed rows (report skeleton, no
    # --run) grading_coverage falls back to this definitional ratio so
    # `--suite v2` can assert coverage=1.0 and a pass@1 denominator >= 24
    # before spending any model calls.
    definition_gradable = [
        task for task in tasks
        if isinstance(task.get("grader"), dict) or task.get("verify_command")
    ]
    return {
        "schema_version": 2,
        "generated_at_epoch": time.time(),
        "fixture_count": len(tasks),
        "executed_count": len(completed),
        "results": rows,
        "metrics": {
            # pass_at_1 counts only tasks with an automated grader; tasks
            # without verify_command report passed=None and must not dilute
            # the pass-rate denominator.
            "pass_at_1": round(len(passed) / len(gradable), 4) if gradable else None,
            "execution_completion_rate": round(sum(row["status"] == "completed" for row in completed) / len(completed), 4) if completed else None,
            "grading_coverage": round(len(gradable) / len(completed), 4) if completed else (round(len(definition_gradable) / len(tasks), 4) if tasks else None),
            "gradable_task_count": len(gradable) if completed else len(definition_gradable),
            "acceptance_success_rate": round(len(passed) / len(gradable), 4) if gradable else None,
            "false_completion_rate": round(sum(row["claimed_complete"] and row["passed"] is False for row in gradable) / len(gradable), 4) if gradable else None,
            "tokens_per_success": round(sum(float(row["usage"]["total_tokens"]) for row in completed) / len(passed), 1) if passed and total_tokens_known else None,
            "cost_per_success_usd": round(sum(row["cost_usd"] for row in completed) / len(passed), 6) if passed and total_cost_known else None,
            "latency_p50_ms": _quantile(latencies, 0.5),
            "latency_p95_ms": _quantile(latencies, 0.95),
            "mean_repair_attempts": round(statistics.mean(repairs), 3) if repairs else None,
            "tool_repeat_rate": round(repeated / calls, 4) if calls and all(_measurement(row["tool_calls"]) and _measurement(row["repeated_tool_calls"]) and row["repeated_tool_calls"] <= row["tool_calls"] for row in completed) else None,
            "token_usage_available": sum(1 for row in completed if row["usage"] is not None),
            "cost_available": sum(1 for row in completed if row["cost_usd"] is not None),
        },
        "notes": [
            "not_run is not a pass or failure.",
            "pass_at_1 is the acceptance rate on graded cases only; ungraded cases are excluded and coverage is reported separately.",
            "Command graders and fake-provider runs do not establish real-world coding accuracy.",
            "Token and cost metrics remain null when the provider does not expose usage or pricing.",
            "Tokens and cost per success include expenditure on failed attempts; missing measurements keep these metrics null.",
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
    for key in ("execution_completion_rate", "grading_coverage", "gradable_task_count", "acceptance_success_rate", "false_completion_rate", "pass_at_1", "latency_p50_ms", "latency_p95_ms", "tokens_per_success", "cost_per_success_usd", "mean_repair_attempts", "tool_repeat_rate", "token_usage_available", "cost_available"):
        lines.append(f"| {key} | {value(metrics.get(key))} |")
    lines.extend(["", "| Task | Category | Status | Passed |", "| --- | --- | --- | --- |"])
    for row in report["results"]:
        lines.append(f"| {row['task_id']} | {row['category']} | {row['status']} | {value(row['passed'])} |")
    lines.extend(["", *[f"- {note}" for note in report["notes"]], ""])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# M4-T7: retrieval decision gate (lexical hit-rate baseline)
# ---------------------------------------------------------------------------


def load_retrieval_cases(path: Path = DEFAULT_RETRIEVAL) -> dict[str, Any]:
    """Load and validate the retrieval hit-rate dataset."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("retrieval 数据集必须是对象")
    cases = raw.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("retrieval 数据集必须包含至少一条 case")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"]:
            raise ValueError("每条 retrieval case 必须包含非空 id")
        if case["id"] in seen:
            raise ValueError(f"retrieval case id 重复: {case['id']}")
        seen.add(case["id"])
        if not isinstance(case.get("query"), str) or not case["query"].strip():
            raise ValueError(f"retrieval case {case['id']} 缺少非空 query")
        targets = case.get("targets")
        if not isinstance(targets, list) or not targets or not all(
            isinstance(t, str) and t and not t.startswith("/") and ".." not in t.split("/")
            for t in targets
        ):
            raise ValueError(f"retrieval case {case['id']} 的 targets 必须是非空、不逃逸的相对路径列表")
    ks = raw.get("ks") or [1, 5]
    if not isinstance(ks, list) or not all(isinstance(k, int) and k >= 1 for k in ks):
        raise ValueError("retrieval ks 必须是 >=1 的整数列表")
    return {"workspace": str(raw.get("workspace") or "."), "ks": sorted(set(ks)), "cases": cases}


def evaluate_retrieval(
    cases: list[dict[str, Any]],
    *,
    workspace: Path,
    ks: Sequence[int] = (1, 5),
) -> dict[str, Any]:
    """Score the deterministic lexical index against known-answer queries.

    recall@k = |targets ∩ top-k| / |targets| averaged over cases; MRR uses the
    rank of the first relevant target. Builds the index once and reuses it.
    """
    from .agent.retrieval import LocalEvidenceIndex

    ks = sorted({int(k) for k in ks if int(k) >= 1}) or [1]
    top_k = max(ks)
    index = LocalEvidenceIndex(workspace)
    rows: list[dict[str, Any]] = []
    recall_sums = {k: 0.0 for k in ks}
    hit_sums = {k: 0 for k in ks}
    reciprocal_ranks: list[float] = []
    for case in cases:
        targets = {str(t).replace("\\", "/") for t in case["targets"]}
        hits = index.search(str(case["query"]), limit=top_k)
        ranked = [hit.path.replace("\\", "/") for hit in hits]
        first_rank = next((i + 1 for i, path in enumerate(ranked) if path in targets), None)
        reciprocal_ranks.append(1.0 / first_rank if first_rank else 0.0)
        row: dict[str, Any] = {
            "id": case["id"],
            "query": case["query"],
            "targets": sorted(targets),
            "first_relevant_rank": first_rank,
            "top": ranked[:top_k],
        }
        for k in ks:
            window = set(ranked[:k])
            recall = len(targets & window) / len(targets)
            recall_sums[k] += recall
            hit_sums[k] += int(recall > 0.0)
            row[f"recall@{k}"] = round(recall, 4)
        rows.append(row)
    n = len(cases)
    metrics: dict[str, Any] = {"mrr": round(sum(reciprocal_ranks) / n, 4) if n else None}
    for k in ks:
        metrics[f"recall@{k}"] = round(recall_sums[k] / n, 4) if n else None
        metrics[f"hit@{k}"] = round(hit_sums[k] / n, 4) if n else None
    return {
        "schema_version": 1,
        "workspace": str(workspace),
        "case_count": n,
        "ks": ks,
        "metrics": metrics,
        "results": rows,
    }


def retrieval_decision(recall_at_5: float | None, floor: float = RETRIEVAL_RECALL_FLOOR) -> str:
    """Written M4-T7 conclusion: introduce embeddings only below the floor."""
    if recall_at_5 is None:
        return "recall@5 不可用（无 case），无法判定；保持现状不引入向量检索。"
    if recall_at_5 < floor:
        return (
            f"recall@5={recall_at_5:.4f} < {floor:.2f}：lexical 基线不达标，"
            "下一步评估引入本地 embedding（sentence-transformers 本地推理，"
            "不用外部向量库），且必须附 A/B 对比数据。"
        )
    return (
        f"recall@5={recall_at_5:.4f} >= {floor:.2f}：lexical 基线达标，"
        "**不引入向量检索**，停止在 embedding 上的投入。"
    )


def markdown_retrieval(report: dict[str, Any], decision: str) -> str:
    metrics = report["metrics"]
    lines = [
        "# minicc Retrieval Hit-Rate (M4-T7 lexical baseline)",
        "",
        f"Workspace: {report['workspace']} | Cases: {report['case_count']}",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key in sorted(metrics):
        lines.append(f"| {key} | {'N/A' if metrics[key] is None else metrics[key]} |")
    lines.extend(["", "| Case | First rank | recall@1 | recall@5 | Target |", "| --- | ---: | ---: | ---: | --- |"])
    for row in report["results"]:
        lines.append(
            f"| {row['id']} | {row['first_relevant_rank'] if row['first_relevant_rank'] else '—'} "
            f"| {row.get('recall@1', 'N/A')} | {row.get('recall@5', 'N/A')} | {', '.join(row['targets'])} |"
        )
    lines.extend(["", f"## 结论", "", decision, ""])
    return "\n".join(lines)


def _run_retrieval_suite(args: argparse.Namespace) -> int:
    dataset_path = args.fixtures if args.fixtures != DEFAULT_FIXTURES else DEFAULT_RETRIEVAL
    try:
        dataset = load_retrieval_cases(dataset_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        cli_out(f"[retrieval] 数据集加载失败: {exc}")
        return 2
    workspace = (REPO_ROOT / dataset["workspace"]).resolve()
    report = evaluate_retrieval(dataset["cases"], workspace=workspace, ks=dataset["ks"])
    decision = retrieval_decision(report["metrics"].get("recall@5"))
    report["decision"] = decision
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown_out.write_text(markdown_retrieval(report, decision), encoding="utf-8")
    metrics = report["metrics"]
    cli_out(
        "[retrieval] "
        + " ".join(f"{k}={metrics[k]}" for k in sorted(metrics))
        + f" | cases={report['case_count']}"
    )
    cli_out(f"[retrieval] 结论: {decision}")
    # CI records these numbers but does not gate on them in the first round.
    return 0


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    # `compare` is a subcommand: `python -m minicc.benchmarks compare ...`.
    # Dispatch before the report parser so its flags never collide, and import
    # lazily to avoid a circular import (bench_compare is standalone).
    if raw and raw[0] == "compare":
        from . import bench_compare
        return bench_compare.main(raw[1:])
    parser = argparse.ArgumentParser(description="生成 minicc 离线评测报告")
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--suite", choices=("legacy", "behavior", "v2", "retrieval"), default="legacy")
    parser.add_argument("--grader-dir", type=Path, help="v2 套件隐藏 grader 脚本目录（默认仓库外 .graders）")
    parser.add_argument("--results", type=Path)
    parser.add_argument("--json-out", type=Path, default=Path("output/evaluation.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("output/evaluation.md"))
    parser.add_argument(
        "--run", action="store_true",
        help="实际执行评测任务（需要真实模型配置）；缺省时只生成报告骨架，不调用模型",
    )
    parser.add_argument("--max-tasks", type=int, help="配合 --run：只执行前 N 条任务")
    parser.add_argument("--task-id", action="append", default=[], help="选择指定任务，可重复传入以进行定向评测")
    parser.add_argument("--no-resume", action="store_true", help="不复用之前完成的评测结果")
    parser.add_argument("--task-timeout", type=float, default=900, help="每条评测任务的超时秒数")
    parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="配合 --run：评测工作区")
    args = parser.parse_args(raw)
    if args.suite == "retrieval":
        return _run_retrieval_suite(args)
    if args.suite == "behavior":
        tasks = behavior_tasks()
    elif args.suite == "v2":
        tasks = bench_tasks.v2_tasks()
        for task in tasks:
            try:
                bench_tasks.validate_task(task)
            except ValueError as exc:
                parser.error(f"tasks.v2.json 校验失败: {exc}")
    else:
        tasks = load_tasks(args.fixtures)
    if args.task_id:
        selected_ids = set(args.task_id)
        missing = selected_ids - {task["id"] for task in tasks}
        if missing:
            parser.error("未知任务 id: " + ", ".join(sorted(missing)))
        tasks = [task for task in tasks if task["id"] in selected_ids]
    if not math.isfinite(args.task_timeout) or args.task_timeout <= 0:
        parser.error("--task-timeout 必须是有限正数")
    results = None
    if args.run:
        results = run_benchmark(
            tasks,
            workspace=args.workspace.expanduser().resolve(),
            max_tasks=args.max_tasks,
            results_path=args.results,
            task_timeout_seconds=args.task_timeout,
            resume=not args.no_resume,
            grader_dir=args.grader_dir.expanduser().resolve() if args.grader_dir else None,
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
    grader_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Execute fixture tasks against the configured real model.

    Requires a live configuration (load_config must succeed with a real
    ``MINICC_API_KEY``); the runner never fabricates results. Each task runs
    through ``AgentService._chat_locked``. Behavior fixtures get an isolated
    temporary workspace and explicit edit permission; legacy tasks stay read-only.
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

    # Evaluation history is isolated from the user's normal task database.
    from .task_store import TaskStore
    if not math.isfinite(float(task_timeout_seconds)) or task_timeout_seconds <= 0:
        raise ValueError("task_timeout_seconds must be a finite positive number")
    grader_dir = bench_tasks.resolve_grader_dir(grader_dir)
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=workspace, capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        revision = ""
    source_hash = hashlib.sha256()
    for path in sorted(Path(__file__).parent.rglob("*.py")):
        source_hash.update(path.relative_to(Path(__file__).parent).as_posix().encode())
        source_hash.update(path.read_bytes())
    # Fingerprint behavior-affecting settings without writing endpoint URLs or
    # secrets. Changing retry/budget/provider settings must invalidate resume.
    config_values = {key: value for key, value in vars(config).items() if key != "api_key"}
    config_hash = hashlib.sha256(json.dumps(config_values, sort_keys=True, default=str).encode()).hexdigest()
    run_metadata = {"model": str(config.model), "reasoning_effort": str(getattr(config, "reasoning_effort", "")), "code_revision": revision, "runtime_source_sha256": source_hash.hexdigest(), "protocol": str(getattr(config, "llm_protocol", "auto")), "fake_provider": os.getenv("MINICC_FAKE_PROVIDER") == "1", "config_sha256": config_hash, "task_timeout_seconds": float(task_timeout_seconds)}
    results: list[dict[str, Any]] = []
    if resume and results_path is not None and results_path.is_file():
        try:
            prior = json.loads(results_path.read_text(encoding="utf-8"))
            if isinstance(prior, list):
                current_tasks = {task["id"]: task for task in tasks}
                # Discard stale rows as well as refusing to skip them. Otherwise
                # a limited rerun silently mixes old-model and current results.
                matching = {item["task_id"]: item for item in prior
                            if isinstance(item, dict) and isinstance(item.get("task_id"), str) and item["task_id"] in current_tasks
                            and _resume_matches(item, current_tasks[item["task_id"]], run_metadata)}
                results = list(matching.values())
        except (OSError, json.JSONDecodeError):
            results = []
    done_ids = {str(item.get("task_id")) for item in results if item.get("status") == "completed"}
    eval_state = tempfile.TemporaryDirectory(prefix="minicc-eval-state-")
    try:
        service = AgentService(workspace, config, task_store=TaskStore(Path(eval_state.name) / "tasks.sqlite3"))
    except BaseException:
        eval_state.cleanup()
        raise
    abandoned_worker: threading.Thread | None = None
    try:
        selected = tasks if max_tasks is None else tasks[: max(0, int(max_tasks))]
        for task in selected:
            if task["id"] in done_ids:
                continue
            started = time.monotonic()
            temporary = tempfile.TemporaryDirectory(prefix="minicc-behavior-") if task.get("fixture") else None
            task_workspace = Path(temporary.name) if temporary else workspace
            cancel = threading.Event()
            worker: threading.Thread | None = None
            interrupted: BaseException | None = None
            outcome: dict[str, Any] = {}
            entry: dict[str, Any] = {"task_id": task["id"], "status": "failed", "passed": None,
                "metadata": {**run_metadata, "suite_version": task.get("suite_version", "legacy-1"), "fixture_sha256": fixture_digest(task)}}
            try:
                if temporary:
                    prepare_fixture(task, task_workspace, initialize_git=True)
                # The chat call is sync; bound it with a daemon worker so a
                # stalled model request cannot freeze the whole evaluation.
                # A daemon thread is abandoned on timeout instead of blocking
                # the run for a gateway that may hang indefinitely.
                outcome_box: dict[str, Any] = {}

                def _run_task(current_task=task, current_workspace=task_workspace, current_cancel=cancel, box=outcome_box) -> None:
                    try:
                        box["outcome"] = service._chat_locked(
                            {
                                "message": str(current_task.get("prompt") or ""),
                                "session_id": f"bench-{current_task['id']}-{uuid.uuid4().hex[:8]}",
                                "allow_changes": bool(current_task.get("fixture")),
                                "allow_network": False,
                                "workspace_path": str(current_workspace),
                            },
                            workspace=current_workspace, cancel_event=current_cancel,
                        )
                    except BaseException as exc:  # noqa: BLE001 - forwarded below
                        box["error"] = exc

                worker = _threading.Thread(
                    target=_run_task, daemon=True, name=f"bench-{task['id']}"
                )
                worker.start()
                worker.join(timeout=float(task_timeout_seconds))
                if worker.is_alive():
                    cancel.set()
                    worker.join(timeout=5)
                    if worker.is_alive():
                        abandoned_worker = worker
                    raise TimeoutError(f"task timeout > {task_timeout_seconds:g}s")
                if "error" in outcome_box:
                    raise outcome_box["error"]
                outcome = outcome_box["outcome"]
            except TimeoutError:
                entry["status"] = "failed"
                entry["error"] = f"task timeout > {task_timeout_seconds:g}s"
            except Exception as exc:  # noqa: BLE001 - one task must not kill the run
                entry["status"] = "failed"
                entry["error"] = f"{type(exc).__name__}: {exc}"[:200]
            except BaseException as exc:
                # Ctrl+C is still propagated, after a durable cancellation
                # record. It must not close providers or remove a fixture that
                # an in-flight SDK call may continue using.
                cancel.set()
                if worker is not None and worker.is_alive():
                    worker.join(timeout=5)
                    if worker.is_alive():
                        abandoned_worker = worker
                interrupted = exc
                entry["status"] = "interrupted"
                entry["error"] = type(exc).__name__
            else:
                completion_status = (outcome.get("completion") or {}).get("status")
                if outcome.get("cancelled"):
                    entry["status"] = "cancelled"
                elif outcome.get("error"):
                    entry["status"] = "failed"
                elif completion_status is not None and completion_status != "complete":
                    entry["status"] = "incomplete"
                else:
                    entry["status"] = "completed"
                entry["turns"] = int(outcome.get("turns") or 0)
                entry["tool_calls"] = int(outcome.get("tool_calls_total") or 0)
                entry["claimed_complete"] = not outcome.get("cancelled") and (completion_status == "complete" if completion_status is not None else not outcome.get("error"))
                entry["repair_attempts"] = (outcome.get("metrics") or {}).get("repair_attempts")
                usage = outcome.get("tokens_used")
                if isinstance(usage, dict):
                    entry["usage"] = usage
                    entry["cost_usd"] = pricing.cost_usd(
                        str(outcome.get("model") or config.model), usage
                    )
                if outcome.get("error"):
                    entry["error"] = str(outcome["error"])[:200]
            entry["execution_latency_ms"] = round((time.monotonic() - started) * 1000, 1)
            grading_started = time.monotonic()

            verify_command = task.get("verify_command")
            if task.get("grader"):
                if entry["status"] == "completed":
                    try:
                        grader_type = (task.get("grader") or {}).get("type")
                        if grader_type in bench_tasks.GRADER_TYPES:
                            entry.update(grade_v2(
                                task, task_workspace,
                                str(outcome.get("answer") or ""), grader_dir=grader_dir,
                            ))
                        else:
                            entry.update(grade_behavior(task, task_workspace, str(outcome.get("answer") or "")))
                    except (ValueError, TypeError, OSError) as exc:
                        entry.update(passed=False, grader_type="invalid", grading_error=f"{type(exc).__name__}: {exc}"[:200])
                else:
                    entry.update(passed=False, grader_type=task["grader"].get("type", "behavior"))
            elif verify_command and entry["status"] == "completed":
                try:
                    completed = _subprocess.run(
                        str(verify_command), cwd=str(task_workspace), shell=True,
                        capture_output=True, text=True, timeout=300,
                    )
                    entry["passed"] = completed.returncode == 0
                except (_subprocess.TimeoutExpired, OSError):
                    entry["passed"] = False
                entry["grader_type"] = "command"
            elif verify_command:
                entry.update(passed=False, grader_type="command")
            entry["grading_latency_ms"] = round((time.monotonic() - grading_started) * 1000, 1)
            entry["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
            if temporary:
                if worker is not None and worker.is_alive():
                    # Never delete a directory while a timed-out worker can
                    # still access it. Preserve it for explicit inspection.
                    temporary._finalizer.detach()
                    entry["retained_workspace"] = str(task_workspace)
                else:
                    try:
                        temporary.cleanup()
                    except OSError as exc:
                        entry["cleanup_error"] = type(exc).__name__
                        entry["retained_workspace"] = str(task_workspace)
            results = [item for item in results if item.get("task_id") != task["id"]]
            results.append(entry)
            if results_path is not None:
                _write_results(results_path, results)
            if interrupted is not None:
                raise interrupted
            if abandoned_worker is not None:
                # A Python thread cannot be killed safely. Do not launch more
                # model requests while this one still owns the shared service.
                break
    finally:
        if abandoned_worker is None:
            try:
                service.shutdown()
            finally:
                eval_state.cleanup()
        else:
            # Keep providers/state valid until the in-flight call observes
            # cancellation. Cleanup must never race a still-running task.
            def deferred_cleanup() -> None:
                abandoned_worker.join()
                try:
                    service.shutdown()
                finally:
                    eval_state.cleanup()
            threading.Thread(target=deferred_cleanup, daemon=True, name="bench-cleanup").start()
    return results


if __name__ == "__main__":
    raise SystemExit(main())
