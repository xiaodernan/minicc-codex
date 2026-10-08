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
from .behavior_bench import (behavior_tasks, fixture_digest, grade_behavior,
                            prepare_fixture, validate_behavior_task)
from . import bench_tasks
from .bench_tasks import LEGACY_SUITE_VERSION, grade_v2
from . import pricing
from .cli_io import cli_out


DEFAULT_FIXTURES = Path(__file__).resolve().parent.parent / "benchmarks" / "tasks.json"
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RETRIEVAL = REPO_ROOT / "benchmarks" / "retrieval-hitrate.json"
# M4-T7 decision rule: only introduce a local embedding model when the lexical
# baseline cannot reliably localize known answers. The roadmap fixes the bar at
# recall@5 < 0.6.
RETRIEVAL_RECALL_FLOOR = 0.6


#: How much of the completion judge's verdict history a failed task keeps.
#: Without this the objective grader is the only signal left, and it is skipped
#: for tasks the judge capped - so a non-converging run produces a failure
#: message with no record of what the reviewer kept asking for.
_REVIEW_ROUNDS_KEPT = 8
_REVIEW_TEXT_CHARS = 200


def _review_rounds(events: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bounded digest of each completion-judge round, for post-mortem reading."""
    rounds: list[dict[str, Any]] = []
    for event in events or ():
        if not isinstance(event, dict) or event.get("name") != "completion_judge":
            continue
        detail = event.get("detail") if isinstance(event.get("detail"), dict) else {}
        rounds.append({
            "code": str(event.get("code") or ""),
            "status": str(detail.get("status") or ""),
            "rationale": str(detail.get("rationale") or "")[:_REVIEW_TEXT_CHARS],
            "missing": [str(item)[:_REVIEW_TEXT_CHARS] for item in (detail.get("missing") or [])[:6]],
            "next_action": str(detail.get("next_action") or "")[:_REVIEW_TEXT_CHARS],
        })
    return rounds[-_REVIEW_ROUNDS_KEPT:]


def _objective_oracle(task: dict[str, Any], workspace: Path, grader_dir: Path | None,
                      worker: threading.Thread | None) -> dict[str, Any] | None:
    """What the deterministic grader sees when the run never reached grading.

    Grading is skipped unless the agent reported completion, so a task the
    completion judge capped is recorded as failed without ever being checked: a
    reviewer false negative looks exactly like missing work. Diagnostic only -
    this never writes ``passed``, so suite scores stay unchanged.
    """
    if worker is not None and worker.is_alive():
        return None  # an abandoned thread may still be writing the workspace
    grader = task.get("grader") or {}
    if grader.get("type") not in bench_tasks.GRADER_TYPES:
        return None
    try:
        result = grade_v2(task, workspace, grader_dir=grader_dir)
    except (ValueError, TypeError, OSError) as exc:
        return {"error": f"{type(exc).__name__}: {exc}"[:200]}
    return dict(result)


def _measurement(value: object) -> bool:
    """Metrics accept actual finite, nonnegative measurements, not bools."""
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


#: Rows whose run never produced graded model work (provider call died:
#: 429 quota, connection error, HTTP-layer timeout) share the unified
#: "LLM 调用失败" error prefix from agent/loop.py:899. That is a property
#: of the environment, not of the model, so it is counted separately
#: (M8-T154) instead of silently reading as a model zero.
_INFRA_ERROR_PREFIX = "LLM 调用失败"


def _is_infra_failure(row: dict[str, Any]) -> bool:
    return row.get("passed") is False and (row.get("error") or "").startswith(_INFRA_ERROR_PREFIX)


def _declared_grader_type(task: dict[str, Any]) -> str:
    """Who would have judged this task, for the rows where nobody got to.

    One owner for the runner's refusal vocabulary: when the host could not write
    the workspace, the row has to say which grader *would* have judged it, and
    this is that answer. ``build_report`` does not use it - since M8-T181 the
    report never derives a judge from the task spec, so a row that recorded no
    grader reports none instead of one the spec implies.
    """
    kind = (task.get("grader") or {}).get("type")
    if isinstance(kind, str) and kind:
        return kind
    return "command" if task.get("verify_command") else "ungraded"


VACUOUS_ORACLE_POLICY = "allow"  # "allow" | "deny" | "require_case_count"

def _oracle_says_pass(row: dict[str, Any]) -> bool:
    """Did the objective grader re-run this row and pass it on real work?

    A ``file_contract`` with an empty ``files`` list prints its own completion
    marker for zero cases (measured: ``{'passed': True, 'case_count': 0}``), so
    its pass judges nothing. When the oracle reports a case count it therefore
    has to report at least one case. When it reports none, the trust is not free:
    it is only extended to a grader type the shipped vocabulary knows, whose
    marker is printed after real work ran. An oracle from a producer nobody knows
    - a legacy results row, or a grader type added later that forgot to count -
    cannot borrow that justification.

    Vacuous oracle policy is controlled by ``VACUOUS_ORACLE_POLICY``:
    - "allow" (default): vacuous oracle passes if its grader_type is known.
    - "deny": vacuous oracle always fails.
    - "require_case_count": vacuous oracle fails unless it has a case_count >= 1.
    """
    oracle = row.get("objective_oracle")
    if not isinstance(oracle, dict) or oracle.get("passed") is not True:
        return False
    if "case_count" in oracle:
        count = oracle["case_count"]
        return _measurement(count) and count >= 1
    # vacuous oracle: no case_count
    policy = VACUOUS_ORACLE_POLICY
    if policy not in ("allow", "deny", "require_case_count"):
        # Unknown policy -> safe default (deny)
        return False
    if policy == "deny" or policy == "require_case_count":
        return False
    return row.get("grader_type") in bench_tasks.GRADER_TYPES


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
            raise ValueError("每个任务必须有 id")
        if task["id"] in seen:
            raise ValueError(f"任务 id 重复: {task['id']}")
        # Same owner the v2 door uses: a blank prompt would still buy a full agent run.
        bench_tasks.require_prompt(task)
        # And a field the report or the shell would have to invent is refused here too.
        bench_tasks.require_objective_shape(task)
        # A fixture the write path has to coerce or cannot open is the same class of lie:
        # the agent is charged for a workspace the host could not author.
        bench_tasks.require_writable_fixture(task)
        # Behavior tasks must also pass their own load-time door (function/fixture
        # consistency) so the agent never starts on a task the grader will refuse.
        grader = task.get("grader") if isinstance(task, dict) else None
        if isinstance(grader, dict) and grader.get("type") == "python_behavior":
            validate_behavior_task(task)
        # A task may declare one objective check, not two: the runner's grader branch wins
        # and the other is dropped without a word, so a task carrying both scores less than
        # its author thinks it does.
        if task.get("grader") and task.get("verify_command"):
            raise ValueError(
                f"任务 {task['id']} 同时声明 grader 和 verify_command，"
                f"verify_command 将被 grader({(task['grader'] or {}).get('type')!r}) 掩盖"
            )
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
            # M8-T118 retired `repeated_tool_calls` here: no producer ever wrote
            # it, so the copy fed only a permanently null metric. Do not restore
            # the line without a writer; the row census guards the hole both ways.
            "usage": recorded.get("usage") if isinstance(recorded.get("usage"), dict) else None,
            "cost_usd": recorded.get("cost_usd") if _measurement(recorded.get("cost_usd")) else None,
            "claimed_complete": recorded.get("claimed_complete", recorded.get("status") == "completed"),
            # M8-T181: no invention. A row that carries a status but no
            # ``grader_type`` names nobody - the task spec says who *would*
            # judge it, which is not the same claim, and the report is the one
            # place a reader cannot tell the two apart. ``not_run`` rows have
            # said None since M8-T139; the other statuses now agree with them.
            "grader_type": (recorded.get("grader_type")
                            if recorded.get("status", "not_run") != "not_run" else None),
            # Rows are rebuilt key by key, so a field the grader added is invisible
            # downstream unless it is copied here (M8-T81 gate).
            "grading_refused": bool(recorded.get("grading_refused")),
            "refusal": (str(recorded.get("refusal") or "")[:300] or None),
            # A failed task records WHY in `entry["error"]`; without this copy
            # the report prints a bare "failed" and the reason vanishes (M8-T81
            # shape). An interrupted task uses the refusal channel instead
            # (M8-T113): nobody judged that workspace.
            "error": (str(recorded.get("error") or "")[:200] or None),
            # M8-T81 shape again: this dict is written by the runner and read by
            # tests off the results JSON, but a row that does not copy it cannot
            # show a reviewer false negative to a human.
            "objective_oracle": (recorded.get("objective_oracle")
                                 if isinstance(recorded.get("objective_oracle"), dict) else None),
            # The rebuild is a second master of "which fields exist", so every key
            # the runner can write has to appear here; a forgotten one is on disk
            # and nowhere a human reads (M8-T89 census).
            "turns": recorded.get("turns") if _measurement(recorded.get("turns")) else None,
            "review_rounds": (recorded.get("review_rounds")
                             # M8-T118: the runner writes rounds as a list of dicts, but
                             # the old copy guard only passed int/float - every real
                             # list was dropped to None and the markdown question was
                             # moot. Accept the produced shape; anything else is None.
                             if isinstance(recorded.get("review_rounds"), list)
                             and all(isinstance(item, dict) for item in recorded["review_rounds"])
                             else None),
            "case_count": recorded.get("case_count")
                          if _measurement(recorded.get("case_count")) else None,
            # A grader killed by a signal reports a negative code, so this must not
            # go through the nonnegative measurement guard the counts use.
            "exit_code": recorded.get("exit_code")
                         if type(recorded.get("exit_code")) is int else None,
            "retained_workspace": (str(recorded.get("retained_workspace") or "")[:300] or None),
            "cleanup_error": (str(recorded.get("cleanup_error") or "")[:200] or None),
            "metadata": recorded.get("metadata"),
        }
        rows.append(row)
    completed = [row for row in rows if row["status"] != "not_run"]
    # M8-T184: which tasks actually ran, so the third verdict can be counted from
    # the task definitions rather than inferred from what a row happens to carry.
    executed_ids = {row["task_id"] for row in completed}
    passed = [row for row in completed if row["passed"] is True]
    gradable = [row for row in completed if row["passed"] is not None]
    latencies = [float(row["latency_ms"]) for row in completed if _measurement(row["latency_ms"])]
    repairs = [int(row["repair_attempts"]) for row in completed if _measurement(row["repair_attempts"])]
    # M8-T118: the `repeated`/`calls` accumulators fed only `tool_repeat_rate`;
    # they left with the metric rather than lingering as dead sums.
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
        # M8-T159: which task suite this report describes, inferred from the
        # task set itself (legacy-shape tasks infer legacy-1). A comparator
        # needs this to refuse cross-suite comparisons instead of silently
        # aligning zero tasks across two disjoint id spaces.
        "suite_version": (
            suite_versions.pop() if len(suite_versions := {str(task.get("suite_version", LEGACY_SUITE_VERSION)) for task in tasks}) == 1
            else "mixed"
        ),
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
            # A grader that could not judge is not a failed task and not an
            # ungraded one either; without its own column a report reader only
            # sees the denominator shrink (M8-T80 wrote the field, nothing read it).
            "grading_refusal_count": sum(1 for row in completed if row.get("grading_refused")),
            # M8-T184: the third verdict, defined by the task and not by the row.
            # ``gradable`` is selected by ``passed is not None`` and the refusal
            # count by ``grading_refused``; a task that declares neither a grader
            # nor a verify_command is ungraded without being a refusal, because
            # the runner never writes ``passed`` for it at all. Asking the *row*
            # instead ("passed is None and not refused") would be the shorter
            # expression and the wrong one: a resumed results file that lost a
            # ``passed`` key would then be reported as a task that never had a
            # grader, which is a claim about the suite the row cannot support.
            # Silence is the acceptable failure here, a lie is not.
            "no_grader_count": sum(
                1 for task in tasks
                if str(task.get("id")) in executed_ids
                and not (isinstance(task.get("grader"), dict) or task.get("verify_command"))
            ),
            # M8-T154: pass_at_1 keeps its frozen denominator (graded rows,
            # infra failures included) so history stays comparable; the two
            # fields below make "the gateway was down" readable instead of
            # masquerading as a model zero.
            "infra_failure_count": sum(1 for row in completed if _is_infra_failure(row)),
            "pass_at_1_ex_infra": (
                round(sum(_is_infra_failure(row) is False and row["passed"] is True for row in non_infra_gradable) / len(non_infra_gradable), 4)
                if (non_infra_gradable := [row for row in gradable if not _is_infra_failure(row)])
                else None
            ),
            "acceptance_success_rate": round(len(passed) / len(gradable), 4) if gradable else None,
            "false_completion_rate": round(sum(row["claimed_complete"] and row["passed"] is False for row in gradable) / len(gradable), 4) if gradable else None,
            # The mirror image of false_completion_rate: grading is skipped unless the
            # agent claimed completion, so a task the completion judge capped is
            # recorded failed without ever being checked. `objective_oracle` re-runs
            # the deterministic grader as a diagnostic, so this counts the rows the
            # reviewer said no about while the grader says yes (M8-T86). An oracle
            # that looked at zero cases is not a yes about anything (M8-T87).
            "reviewer_false_negative_count": sum(
                1 for row in completed
                if row["passed"] is False and _oracle_says_pass(row)
            ),
            "tokens_per_success": round(sum(float(row["usage"]["total_tokens"]) for row in completed) / len(passed), 1) if passed and total_tokens_known else None,
            "cost_per_success_usd": round(sum(row["cost_usd"] for row in completed) / len(passed), 6) if passed and total_cost_known else None,
            "latency_p50_ms": _quantile(latencies, 0.5),
            "latency_p95_ms": _quantile(latencies, 0.95),
            "mean_repair_attempts": round(statistics.mean(repairs), 3) if repairs else None,
            # M8-T118: `tool_repeat_rate` was deleted, not nulled. It read a key
            # no producer ever wrote, so every report in history printed N/A for
            # it; a permanently null row teaches readers to ignore the table.
            # The formula is in git history if a repeat counter ever gets a writer.
            "token_usage_available": sum(1 for row in completed if row["usage"] is not None),
            "cost_available": sum(1 for row in completed if row["cost_usd"] is not None),
        },
        "notes": [
            "not_run is not a pass or failure.",
            "pass_at_1 is the acceptance rate on graded cases only; ungraded cases are excluded and coverage is reported separately.",
        "infra_failure_count counts rows that failed before any graded work happened (provider call errors); pass_at_1_ex_infra excludes them, while pass_at_1 keeps its denominator unchanged.",
            "Command graders and fake-provider runs do not establish real-world coding accuracy.",
            "Token and cost metrics remain null when the provider does not expose usage or pricing.",
            "Tokens and cost per success include expenditure on failed attempts; missing measurements keep these metrics null.",
            "REFUSED means nobody judged this workspace: the grader declined (exit 2), could not be run, the host could not write the workspace, or the operator aborted the run; it is not a pass, a failure, or a task without a grader.",
            "Every executed row lands in exactly one of three verdicts: judged (gradable_task_count), refused (grading_refusal_count), or no grader at all (no_grader_count). grading_coverage is the judged share, so the two counts together say what the rest of the denominator is made of - a task with no grader and no verify_command was never going to be judged, which is a property of the suite, not of the run.",
            "reviewer_false_negative_count counts rows recorded failed whose objective grader, re-run only as a diagnostic, reports passed; it measures the reviewer, not the suite score. An oracle that reports zero cases checked nothing, so its pass does not count, and one that names no known grader is not trusted either.",
        ],
    }


def markdown_report(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    def value(item: object, row: dict[str, Any] | None = None) -> str:
        if item is None:
            return "REFUSED" if row and row.get("grading_refused") else "N/A"
        return str(item)
    lines = [
        "# minicc Evaluation Report",
        "",
        f"Fixtures: {report['fixture_count']} | Executed: {report['executed_count']}",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    # The printed list is derived from the metrics dict, not hand-written beside it:
    # a hand-written copy is a second owner of "which metrics exist" and silently
    # drops any key added to only one of the two places (M8-T86). The declared
    # reading order is honoured, then every remaining key is printed in sorted order.
    preferred = ("execution_completion_rate", "grading_coverage", "gradable_task_count", "grading_refusal_count", "no_grader_count", "acceptance_success_rate", "false_completion_rate", "reviewer_false_negative_count", "infra_failure_count", "pass_at_1", "pass_at_1_ex_infra", "latency_p50_ms", "latency_p95_ms", "tokens_per_success", "cost_per_success_usd", "mean_repair_attempts", "token_usage_available", "cost_available")
    for key in [k for k in preferred if k in metrics] + sorted(set(metrics) - set(preferred)):
        lines.append(f"| {key} | {value(metrics.get(key))} |")
    lines.extend(["", "| Task | Category | Status | Passed |", "| --- | --- | --- | --- |"])
    for row in report["results"]:
        detail = str(row.get("refusal") or "")[:60]
        verdict = value(row["passed"], row) + (f" ({detail})" if row.get("grading_refused") and detail else "")
        # A non-completed row must show the recorded reason, not just "failed".
        if row.get("error"):
            verdict += f" [{str(row['error'])[:120]}]"
        # M8-T118 印法: the rounds themselves live in the JSON row (bounded: 8
        # rounds, 200 chars each); markdown carries only the count, so a capped
        # run's post-mortem is visible without exploding the four-column table.
        rounds = row.get("review_rounds")
        if isinstance(rounds, list) and rounds:
            count = len(rounds)
            verdict += f" [{count} review round{'s' if count != 1 else ''}]"
        lines.append(f"| {row['task_id']} | {row['category']} | {row['status']} | {verdict} |")
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
    # Scoring under a stated budget is how the truncation behaviour stays testable
    # without a 1200-file fixture; it has to be an explicit number, never a typo.
    budget: dict[str, int] = {}
    for key in ("max_files", "max_directories"):
        value = raw.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"retrieval {key} 必须是 >=1 的整数")
        budget[key] = value
    return {"workspace": str(raw.get("workspace") or "."), "ks": sorted(set(ks)), "cases": cases, **budget}


def evaluate_retrieval(
    cases: list[dict[str, Any]],
    *,
    workspace: Path,
    ks: Sequence[int] = (1, 5),
    max_files: int | None = None,
    max_directories: int | None = None,
) -> dict[str, Any]:
    """Score the deterministic lexical index against known-answer queries.

    recall@k = |targets ∩ top-k| / |targets| averaged over cases; MRR uses the
    rank of the first relevant target. Builds the index once and reuses it, and
    publishes that index's walk census under ``index`` so the numbers below can
    be read as either a retrieval result or a truncated scan.
    """
    from .agent.retrieval import LocalEvidenceIndex

    ks = sorted({int(k) for k in ks if int(k) >= 1}) or [1]
    top_k = max(ks)
    budget: dict[str, int] = {}
    if max_files is not None:
        budget["max_files"] = max_files
    if max_directories is not None:
        budget["max_directories"] = max_directories
    index = LocalEvidenceIndex(workspace, **budget)
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
        "index": index.stats(),
        "metrics": metrics,
        "results": rows,
    }


def retrieval_decision(
    recall_at_5: float | None,
    floor: float = RETRIEVAL_RECALL_FLOOR,
    *,
    index: dict[str, Any] | None = None,
) -> str:
    """Written M4-T7 conclusion: introduce embeddings only below the floor.

    ``index`` is the census of the walk that scored the cases.  Without it the
    denominator is unknown, and an unknown denominator gets neither branch:
    a metric over a prefix of the workspace cannot recommend a vector stack
    either (measured: 1250 files against a 1200 budget produced recall@5=0.0 and
    this function printed the "introduce embeddings" sentence).
    """
    if recall_at_5 is None:
        return "recall@5 不可用（无 case），无法判定；保持现状不引入向量检索。"
    from .agent.retrieval import census_is_complete

    if not census_is_complete(index):
        keys = ("files_indexed", "files_seen", "files_skipped", "file_limit",
                "directories_walked", "directory_budget", "truncated")
        bits = " ".join(
            f"{key}={'未知' if not index or index.get(key) is None else index.get(key)}" for key in keys
        )
        return (
            f"recall@5={recall_at_5:.4f} 但索引遍历口径不完整（截断或分母未知：{bits}）："
            "这个数字衡量的是工作区的一个前缀，既不能判定 lexical 基线达标，"
            "也不能据此启动向量检索的投入；先把候选收集恢复成完整遍历"
            "（调大 max_files/max_directories，或把工作区内的临时目录移走）再重跑。"
        )
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


def _census_line(index: dict[str, Any] | None) -> str:
    """The denominator the metrics were computed over, in the quotable report."""
    from .agent.retrieval import census_is_complete

    if not index:
        return "Index census: 未知（报告里没有索引 stats） | 口径完整=False"
    return (
        f"Index census: files_indexed={index.get('files_indexed')} "
        f"files_seen={index.get('files_seen')} files_skipped={index.get('files_skipped')} "
        f"file_limit={index.get('file_limit')} "
        f"directories={index.get('directories_walked')}/{index.get('directory_budget')} "
        f"truncated={index.get('truncated')} | 口径完整={census_is_complete(index)}"
    )


def markdown_retrieval(report: dict[str, Any], decision: str) -> str:
    metrics = report["metrics"]
    lines = [
        "# minicc Retrieval Hit-Rate (M4-T7 lexical baseline)",
        "",
        f"Workspace: {report['workspace']} | Cases: {report['case_count']}",
        _census_line(report.get("index")),
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
    budget = {key: dataset[key] for key in ("max_files", "max_directories") if key in dataset}
    report = evaluate_retrieval(dataset["cases"], workspace=workspace, ks=dataset["ks"], **budget)
    decision = retrieval_decision(report["metrics"].get("recall@5"), index=report["index"])
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
    cli_out(_census_line(report.get("index")))
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
        for task in tasks:
            # Same shape as the v2 door: an unscoreable task is a broken task file, and
            # finding that out after the agent ran wasted the run.
            try:
                validate_behavior_task(task)
            except ValueError as exc:
                parser.error(f"behavior 任务集校验失败: {exc}")
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
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=workspace, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5).stdout.strip()
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
                "metadata": {**run_metadata, "suite_version": task.get("suite_version", LEGACY_SUITE_VERSION), "fixture_sha256": fixture_digest(task)}}
            # Which stage the host itself got to. ``prepare_fixture`` writes the
            # workspace this task is judged in, so an exception there means no
            # workspace ever existed - and that is nobody's verdict (M8-T107).
            host_stage = "prepare" if temporary else "run"
            try:
                if temporary:
                    prepare_fixture(task, task_workspace, initialize_git=True)
                host_stage = "run"
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
                if host_stage == "prepare":
                    # The host could not write the fixture, so no agent ran and
                    # no grader looked at anything: NO-RESULT, not a failure.
                    # The reason goes to ``refusal`` - the field the report
                    # prints - while ``error`` stays the agent's own diagnostic.
                    entry.update(bench_tasks.workspace_unwritable(
                        _declared_grader_type(task), exc))
                else:
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
                # An interrupt is the operator's, not the agent's and not the
                # host's: the row records how the run ended in `status`, but the
                # verdict is NO-RESULT - nobody judged this workspace, and no
                # grader is started during an abort (M8-T113).
                entry.update(bench_tasks.run_interrupted(
                    _declared_grader_type(task), exc))
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
                if entry["status"] != "completed":
                    entry["review_rounds"] = _review_rounds(outcome.get("events") or ())
            entry["execution_latency_ms"] = round((time.monotonic() - started) * 1000, 1)
            grading_started = time.monotonic()

            verify_command = task.get("verify_command")
            # A row that never had a workspace has no grader to ask and no
            # diagnostic to re-run: the oracle below would judge an empty
            # directory and invent a reviewer false negative (M8-T107).
            refused = bool(entry.get("grading_refused"))
            if task.get("grader"):
                if entry["status"] == "completed":
                    attempted = "behavior"
                    try:
                        grader_type = (task.get("grader") or {}).get("type")
                        if grader_type in bench_tasks.GRADER_TYPES:
                            attempted = str(grader_type)
                            entry.update(grade_v2(
                                task, task_workspace,
                                str(outcome.get("answer") or ""), grader_dir=grader_dir,
                            ))
                        else:
                            entry.update(grade_behavior(task, task_workspace, str(outcome.get("answer") or "")))
                    except (ValueError, TypeError, OSError) as exc:
                        # The grader blew up, not the workspace: same NO-RESULT
                        # shape, and the row keeps the agent's own error.
                        entry.update(bench_tasks.grader_unable(attempted, exc))
                elif not refused:
                    entry.update(passed=False, grader_type=task["grader"].get("type", "behavior"))
                    oracle = _objective_oracle(task, task_workspace, grader_dir, worker)
                    if oracle:
                        entry["objective_oracle"] = oracle
            elif verify_command and entry["status"] == "completed":
                try:
                    completed = _subprocess.run(
                        str(verify_command), cwd=str(task_workspace), shell=True,
                        capture_output=True, text=True, errors="replace", timeout=300,
                    )
                    entry["passed"] = completed.returncode == 0
                    # Inside the try, not after the handler: a write below the
                    # except would re-master grader_type and make the refusal's
                    # own declared type unobservable.
                    entry["grader_type"] = "command"
                except (_subprocess.TimeoutExpired, OSError) as exc:
                    # The host could not start or finish the verify command, so
                    # nobody looked at this workspace: NO-RESULT, the same
                    # channel the contract graders use, not the agent's verdict.
                    entry.update(bench_tasks.grader_unable("command", exc))
            elif verify_command and not refused:
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
