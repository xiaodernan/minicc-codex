"""M8-T85: every key the runner writes into a result row must name its reader.

The runner builds one result row per task and the report rebuilds it key by
key, so a key the report does not copy is invisible downstream (M8-T81). The
mirror image is the defect this batch measured: ``build_report`` divides
``repeated_tool_calls`` into ``tool_repeat_rate`` for every row, and no writer
in ``minicc/`` ever produced that key - the metric could only ever be null
while the report kept printing the row.

"Is there a reader" is not one question. A row is read on three code planes:

* the report plane - ``build_report`` copies keys onto report rows and sums
  them into metrics;
* the comparison plane - ``bench_compare`` accepts report JSON *and* a raw
  results array, so it reads row keys the report never touches;
* the resume plane - ``_resume_matches`` reads the stored row's ``metadata``
  to decide whether a completed row may be reused.

Whatever is left is the durable plane: the row is flushed to the results JSON
and a human (or a later run) reads it there. Those keys are named in
``docs/BENCHMARK_EVALUATION.md`` and this gate checks the document still names
them, so "no code reads this one" is a written decision, not an assumption.

The census is derived from the AST. No line numbers are pinned anywhere: a line
number rots the moment the file moves under it, which is a defect this repo has
already recorded.
"""

from __future__ import annotations

import ast
import asyncio
import functools
import json
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent

# Every module that can put a key on a result row: the runner itself, plus the
# two grader modules whose returned dicts are merged in by ``entry.update``.
SOURCES = {
    path: (REPO_ROOT / path).read_text(encoding="utf-8")
    for path in (
        "minicc/benchmarks.py",
        "minicc/bench_tasks.py",
        "minicc/behavior_bench.py",
        "minicc/bench_compare.py",
    )
}

BENCHMARKS = "minicc/benchmarks.py"
COMPARE = "minicc/bench_compare.py"
EVALUATION_DOC = REPO_ROOT / "docs" / "BENCHMARK_EVALUATION.md"

# key -> the planes that read it. ``doc`` means "no code reader; the evaluation
# document names it as a durable results-JSON field".
# ``agent_code_timed_out`` is the one key the behavior grader adds: it marks a
# failure the host can attribute to the workspace's own code (see
# ``tests/test_grader_clock_attribution.py``), so it has no code reader either.
DECLARED_PLANES: dict[str, frozenset[str]] = {
    "claimed_complete": frozenset({"report"}),
    "cost_usd": frozenset({"report", "compare"}),
    "execution_latency_ms": frozenset({"report"}),
    "grader_type": frozenset({"report"}),
    "grading_latency_ms": frozenset({"report"}),
    "grading_refused": frozenset({"report"}),
    "latency_ms": frozenset({"report", "compare"}),
    "metadata": frozenset({"report", "resume"}),
    "passed": frozenset({"report", "compare"}),
    "refusal": frozenset({"report"}),
    "repair_attempts": frozenset({"report"}),
    "status": frozenset({"report", "compare"}),
    "task_id": frozenset({"report", "compare"}),
    "tool_calls": frozenset({"report"}),
    "usage": frozenset({"report"}),
    "case_count": frozenset({"report"}),
    "cleanup_error": frozenset({"report"}),
    "error": frozenset({"report"}),
    "exit_code": frozenset({"report"}),
    "objective_oracle": frozenset({"report"}),
    "retained_workspace": frozenset({"report"}),
    "review_rounds": frozenset({"report"}),
    "turns": frozenset({"report"}),
}

# The comparator accepts two row shapes the runner never writes: a report row
# (``category`` is added by ``build_report``) and a multi-draw results array
# (``draws`` comes from a harness that ran each task k times - ``bench_compare
# --repeat`` documents the shape). Declared here so the census does not pretend
# its input is always the runner's output.
COMPARE_EXTRA_INPUT: dict[str, str] = {
    "category": "build_report writes it onto every report row the comparator accepts",
    "draws": "a multi-draw producer supplied it; run_benchmark runs each task once",
}


@functools.lru_cache(maxsize=None)
def _functions_of(source: str) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef)
    }


def _returned_keys(module: str, name: str, sources: dict[str, str], seen: frozenset[str] = frozenset()) -> set[str]:
    """String keys of the dict(s) ``name`` returns, following ``return helper()``."""
    if (module, name) in seen or name not in _functions_of(sources[module]):
        return set()
    seen = seen | {(module, name)}
    node = _functions_of(sources[module])[name]
    returned_names = {
        ret.value.id for ret in ast.walk(node)
        if isinstance(ret, ast.Return) and isinstance(ret.value, ast.Name)
    }
    keys: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Return):
            value = sub.value
            if isinstance(value, ast.Dict):
                keys |= {str(k.value) for k in value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            elif isinstance(value, ast.Call):
                func = value.func
                callee = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                for other in sources:
                    keys |= _returned_keys(other, callee, sources, seen)
        if not isinstance(sub, (ast.Assign, ast.AnnAssign)):
            continue
        targets = sub.targets if isinstance(sub, ast.Assign) else [sub.target]
        for target in targets:
            if not isinstance(target, ast.Name) or target.id not in returned_names:
                continue
            if isinstance(sub.value, ast.Dict):
                keys |= {str(k.value) for k in sub.value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        for target in targets:
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id in returned_names
                and isinstance(target.slice, ast.Constant)
                and isinstance(target.slice.value, str)
            ):
                keys.add(target.slice.value)
    return keys


def _row_writer_keys(sources: dict[str, str]) -> set[str]:
    """Every key ``run_benchmark`` can leave on a result row.

    Three write shapes count: the ``entry`` literal, ``entry[key] = ...``
    stores, and ``entry.update(...)`` - whose keyword keys are literal but whose
    positional grader call contributes whatever that grader returns.
    """
    node = _functions_of(sources[BENCHMARKS])["run_benchmark"]
    keys: set[str] = set()
    for sub in ast.walk(node):
        targets = sub.targets if isinstance(sub, ast.Assign) else ([sub.target] if isinstance(sub, ast.AnnAssign) else [])
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "entry" and isinstance(sub.value, ast.Dict):
                keys |= {str(k.value) for k in sub.value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == "entry"
                and isinstance(target.slice, ast.Constant)
                and isinstance(target.slice.value, str)
            ):
                keys.add(target.slice.value)
        if not (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == "update"
            and isinstance(sub.func.value, ast.Name)
            and sub.func.value.id == "entry"
        ):
            continue
        keys |= {keyword.arg for keyword in sub.keywords if keyword.arg}
        for argument in sub.args:
            if not isinstance(argument, ast.Call):
                continue
            func = argument.func
            callee = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            for other in sources:
                keys |= _returned_keys(other, callee, sources)
    return keys


def _reads(node: ast.AST, receivers: set[str]) -> set[str]:
    """String keys read off one of ``receivers`` via ``.get(key)`` or ``[key]``."""
    keys: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == "get" and sub.args:
            owner = sub.func.value
            first = sub.args[0]
            if (
                isinstance(owner, ast.Name)
                and owner.id in receivers
                and isinstance(first, ast.Constant)
                and isinstance(first.value, str)
            ):
                keys.add(first.value)
        if isinstance(sub, ast.Subscript) and isinstance(sub.value, ast.Name) and sub.value.id in receivers:
            if isinstance(sub.slice, ast.Constant) and isinstance(sub.slice.value, str):
                keys.add(sub.slice.value)
    return keys


def _report_reads(sources: dict[str, str]) -> set[str]:
    """Row keys ``build_report`` reads: every rebuilt key plus the row index."""
    return _reads(_functions_of(sources[BENCHMARKS])["build_report"], {"recorded", "row", "item"})


def _resume_reads(sources: dict[str, str]) -> set[str]:
    # ``item`` is the stored row; ``recorded`` is the row's nested metadata dict,
    # so keys read off it (fixture_sha256) belong to that inner dict, not here.
    return _reads(_functions_of(sources[BENCHMARKS])["_resume_matches"], {"item"})


def _compare_reads(sources: dict[str, str]) -> set[str]:
    """Row keys the A/B comparator reads, including from a raw results array."""
    functions = _functions_of(sources[COMPARE])
    keys: set[str] = set()
    for name in ("_normalize_rows", "_index", "_pass_stats", "_cost_per_success", "_latencies", "_pass_at_k"):
        if name in functions:
            keys |= _reads(functions[name], {"row", "recorded", "item"})
    return keys


def _keys_on(plane: str) -> set[str]:
    return {key for key, planes in DECLARED_PLANES.items() if plane in planes}


# --- the census itself -------------------------------------------------------


def test_the_writer_census_and_the_declared_table_are_the_same_set() -> None:
    written = _row_writer_keys(SOURCES)
    undeclared = sorted(written - set(DECLARED_PLANES))
    stale = sorted(set(DECLARED_PLANES) - written)
    assert not undeclared, f"row keys with no declared reader plane: {undeclared}"
    assert not stale, f"table rows the runner no longer writes: {stale}"
    assert len(written) >= 20, f"the writer census went blind: only {sorted(written)}"


def test_every_key_the_report_reads_off_a_row_is_written_by_the_runner() -> None:
    """The M8-T85 defect: a reader whose writer never existed."""
    orphans = sorted(_report_reads(SOURCES) - _row_writer_keys(SOURCES))
    assert orphans == [], f"build_report reads row keys nobody writes: {orphans}"


def test_each_declared_code_plane_really_reads_its_keys() -> None:
    for plane, reader in (
        ("report", _report_reads),
        ("resume", _resume_reads),
        ("compare", _compare_reads),
    ):
        declared = _keys_on(plane)
        observed = reader(SOURCES)
        if plane == "compare":
            observed -= set(COMPARE_EXTRA_INPUT)
        assert declared == observed, (
            f"{plane} plane drifted: declared-but-unread={sorted(declared - observed)} "
            f"read-but-undeclared={sorted(observed - declared)}"
        )


def test_durable_keys_are_named_in_the_evaluation_document() -> None:
    text = EVALUATION_DOC.read_text(encoding="utf-8")
    missing = sorted(key for key in _keys_on("doc") if key not in text)
    assert missing == [], (
        f"durable row keys with no reader and no documentation: {missing} "
        f"- either wire a reader or name them in {EVALUATION_DOC.name}"
    )


def test_the_census_notices_a_new_undeclared_write() -> None:
    """Reverse control: a planted extra store must show up as unclassified."""
    planted = (
        "def run_benchmark(tasks):\n"
        "    for task in tasks:\n"
        "        entry = {'task_id': task, 'status': 'failed'}\n"
        "        entry['passed'] = None\n"
        "        entry['a_field_nobody_declared'] = 1\n"
        "        return entry\n"
    )
    written = _row_writer_keys({**SOURCES, BENCHMARKS: planted})
    assert "a_field_nobody_declared" in written
    assert written - set(DECLARED_PLANES) == {"a_field_nobody_declared"}


def test_the_comparator_input_shape_is_declared_not_assumed() -> None:
    extra = _compare_reads(SOURCES) - _row_writer_keys(SOURCES)
    assert extra == set(COMPARE_EXTRA_INPUT), (
        f"the comparator reads row keys the runner does not write: {sorted(extra)} "
        f"- declared: {sorted(COMPARE_EXTRA_INPUT)}"
    )


def test_the_census_notices_a_reader_without_a_writer() -> None:
    """Reverse control: the orphan check must be able to say orphan."""
    planted = (
        "def build_report(tasks, results=None):\n"
        "    for item in results or []:\n"
        "        return item.get('only_ever_read')\n"
    )
    readers = _report_reads({**SOURCES, BENCHMARKS: planted})
    assert readers == {"only_ever_read"}
    assert readers - _row_writer_keys(SOURCES) == {"only_ever_read"}


# --- the defect this batch fixed, behaviourally ------------------------------


# --- the retired repeat metric (M8-T118) and its census interaction --------

def test_the_retired_repeat_metric_has_no_producer_and_no_report_key(tmp_path, monkeypatch) -> None:
    """M8-T118 retired ``repeated_tool_calls`` / ``tool_repeat_rate`` entirely.

    The archived report on disk carries rows with ``repeated_tool_calls: null``
    and prints ``tool_repeat_rate 0.0`` - the emptied set was summed and the
    zero re-published. The retirement pins that the row never carries the key
    again and the report never prints the metric at all, so a missing writer
    cannot become a fabricated zero.
    """
    from minicc import benchmarks

    class Service:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def _chat_locked(self, payload, **kwargs):
            return {
                "answer": "ok", "turns": 1, "tool_calls_total": 3,
                "metrics": {"repair_attempts": 0},
                "completion": {"status": "complete"},
            }

        def shutdown(self) -> None:
            pass

    monkeypatch.setattr("minicc.web.AgentService", Service)
    monkeypatch.setattr(
        "minicc.config.load_config",
        lambda *args, **kwargs: SimpleNamespace(yolo=False, model="test-model", max_concurrent_tasks=1),
    )
    tasks = [{"id": "t1", "category": "edit", "prompt": "p"}]
    rows = benchmarks.run_benchmark(tasks, workspace=tmp_path)
    assert "repeated_tool_calls" not in rows[0]
    report = benchmarks.build_report(tasks, rows)
    assert "tool_repeat_rate" not in report["metrics"]


def test_a_row_that_never_measured_repeats_cannot_become_a_zero_rate() -> None:
    from minicc.benchmarks import build_report

    rows = [{"task_id": "t", "status": "completed", "passed": True, "tool_calls": 4}]
    report = build_report([{"id": "t", "category": "c"}], rows)
    assert "tool_repeat_rate" not in report["metrics"]
