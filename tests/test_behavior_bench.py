import json
from pathlib import Path

from minicc.behavior_bench import behavior_tasks, prepare_fixture, grade_behavior
from minicc.benchmarks import build_report, _quantile


def test_failed_run_never_counts_as_success():
    tasks = [{"id": "one"}, {"id": "two"}, {"id": "three"}]
    report = build_report(tasks, [{"task_id": "one", "status": "failed", "passed": True}, {"task_id": "two", "status": "completed", "passed": False}, {"task_id": "three", "status": "completed", "passed": None}])
    assert report["metrics"]["pass_at_1"] == 0
    assert report["metrics"]["grading_coverage"] == 0.6667
    assert report["metrics"]["false_completion_rate"] == 0.5


def test_small_sample_percentiles_are_interpolated():
    assert _quantile([100, 200], 0.5) == 150
    assert _quantile([100, 200], 0.95) == 195
    assert _quantile([], 0.95) is None


def test_cost_per_success_includes_failed_attempts_and_requires_complete_usage():
    tasks = [{"id": "success"}, {"id": "failure"}]
    results = [
        {"task_id": "success", "status": "completed", "passed": True, "usage": {"total_tokens": 100}, "cost_usd": 0.1},
        {"task_id": "failure", "status": "failed", "passed": False, "usage": {"total_tokens": 50}, "cost_usd": 0.2},
    ]
    metrics = build_report(tasks, results)["metrics"]
    assert metrics["tokens_per_success"] == 150
    assert metrics["cost_per_success_usd"] == 0.3
    results[1].pop("usage")
    results[1].pop("cost_usd")
    metrics = build_report(tasks, results)["metrics"]
    assert metrics["tokens_per_success"] is None
    assert metrics["cost_per_success_usd"] is None


def test_report_rejects_invalid_measurements():
    metrics = build_report([{"id": "a"}], [{"task_id": "a", "status": "completed", "passed": True,
        "latency_ms": float("nan"), "cost_usd": -1, "usage": {"total_tokens": True},
        "tool_calls": 2, "repeated_tool_calls": 3}])["metrics"]
    assert metrics["latency_p95_ms"] is None
    assert metrics["tokens_per_success"] is None
    assert metrics["cost_per_success_usd"] is None
    assert metrics["tool_repeat_rate"] is None


def test_checked_in_suite_matches_generated_fixtures():
    path = Path(__file__).resolve().parents[1] / "benchmarks" / "behavior-tasks.json"
    assert json.loads(path.read_text(encoding="utf-8")) == behavior_tasks()


def test_every_behavior_fixture_detects_original_bug(tmp_path):
    tasks = behavior_tasks()
    assert len(tasks) == 12
    for task in tasks:
        workspace = tmp_path / task["id"]
        workspace.mkdir()
        prepare_fixture(task, workspace)
        assert not grade_behavior(task, workspace)["passed"], task["id"]
        assert not (workspace / "grader.py").exists()


def test_behavior_grader_accepts_correct_fix_and_rejects_happy_path_only(tmp_path):
    task = behavior_tasks()[0]
    prepare_fixture(task, tmp_path)
    (tmp_path / "solution.py").write_text("def clamp(value, lower, upper):\n    if lower > upper: raise ValueError('bounds')\n    return min(max(value, lower), upper)\n")
    assert grade_behavior(task, tmp_path)["passed"]
    (tmp_path / "solution.py").write_text("def clamp(value, lower, upper):\n    return min(max(value, lower), upper)\n")
    assert not grade_behavior(task, tmp_path)["passed"]


def test_behavior_grader_rejects_early_success_exit(tmp_path):
    task = behavior_tasks()[0]
    prepare_fixture(task, tmp_path)
    (tmp_path / "solution.py").write_text("raise SystemExit(0)\n")
    assert not grade_behavior(task, tmp_path)["passed"]


def test_behavior_grader_rejects_integers_for_boolean_contract(tmp_path):
    task = next(item for item in behavior_tasks() if item["id"] == "behavior-parse_bool")
    prepare_fixture(task, tmp_path)
    (tmp_path / "solution.py").write_text("def parse_bool(text):\n    value=text.strip().lower()\n    if value in ('true','1','yes'): return 1\n    if value in ('false','0','no'): return 0\n    raise ValueError()\n")
    assert not grade_behavior(task, tmp_path)["passed"]


def test_behavior_grader_checks_input_preservation_on_exception(tmp_path):
    task = next(item for item in behavior_tasks() if item["id"] == "behavior-chunks")
    prepare_fixture(task, tmp_path)
    (tmp_path / "solution.py").write_text("def chunks(items, size):\n    if size <= 0:\n        items.clear()\n        raise ValueError()\n    return [items[i:i+size] for i in range(0,len(items),size)]\n")
    assert not grade_behavior(task, tmp_path)["passed"]


def test_behavior_grader_allows_workspace_helper_import(tmp_path):
    task = behavior_tasks()[0]
    prepare_fixture(task, tmp_path)
    (tmp_path / "solution.py").write_text("from helper import clamp\n")
    (tmp_path / "helper.py").write_text("def clamp(value, lower, upper):\n    if lower > upper: raise ValueError('bounds')\n    return min(max(value, lower), upper)\n")
    assert grade_behavior(task, tmp_path)["passed"]


def test_grader_accepts_independent_reference_repairs_for_all_cases(tmp_path):
    repairs = {
        "clamp": "if lower > upper: raise ValueError()\nreturn min(max(value, lower), upper)",
        "chunks": "if size <= 0: raise ValueError()\nreturn [items[i:i+size] for i in range(0,len(items),size)]",
        "dedupe": "result=[]\nfor item in items:\n    if item not in result: result.append(item)\nreturn result",
        "median": "if not items: raise ValueError()\ns=sorted(items); n=len(s)\nreturn s[n//2] if n%2 else (s[n//2-1]+s[n//2])/2",
        "slugify": "import re\nreturn re.sub('[^a-z0-9]+','-',text.lower()).strip('-')",
        "merge_counts": "result={}\nfor item in items:\n    for key,value in item.items(): result[key]=result.get(key,0)+value\nreturn result",
        "parse_bool": "value=text.strip().lower()\nif value in ('true','1','yes'): return True\nif value in ('false','0','no'): return False\nraise ValueError()",
        "paginate": "if page < 1 or size < 1: raise ValueError()\nreturn items[(page-1)*size:page*size]",
        "interval_overlap": "if a[1]<a[0] or b[1]<b[0]: raise ValueError()\nreturn max(0,min(a[1],b[1])-max(a[0],b[0]))",
        "moving_average": "if window <= 0: raise ValueError()\nreturn [sum(items[i:i+window])/window for i in range(len(items)-window+1)]",
        "flatten_once": "return [part for item in items for part in (item if isinstance(item,list) else [item])]",
        "safe_divide": "return default if b==0 else a/b",
    }
    for task in behavior_tasks():
        root=tmp_path / task["id"]
        root.mkdir()
        prepare_fixture(task,root)
        name=task["grader"]["function"]
        signature=task["fixture"]["solution.py"].splitlines()[0]
        (root / "solution.py").write_text(signature + "\n" + "\n".join("    "+line for line in repairs[name].splitlines()) + "\n")
        assert grade_behavior(task,root)["passed"], name
