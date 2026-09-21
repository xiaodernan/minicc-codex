"""M4-T5: v2 writable-fixture suite, hidden graders, and grader-dir blocking.

Covers the acceptance criteria:
  * tasks.v2.json schema (required keys, unique ids, no fixture path escape,
    grader-type whitelist, positive max_minutes, category minimums);
  * file_contract and command_contract graders discriminate (not constant-true);
  * a fake-provider run over two file_contract fixtures yields one pass and one
    failure;
  * read_file / grep / glob / tree on the hidden ``.graders`` directory all
    return TOOL_ERROR.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from minicc import bench_tasks
from minicc.bench_tasks import (
    GRADER_TYPES,
    grade_v2,
    resolve_grader_dir,
    v2_tasks,
    validate_task,
)
from minicc.benchmarks import build_report, run_benchmark
from minicc.tools import Editor, ToolCall, build_registry


# ---------------------------------------------------------------------------
# schema / integrity
# ---------------------------------------------------------------------------


def test_v2_suite_schema_and_counts() -> None:
    tasks = v2_tasks()
    ids = [task["id"] for task in tasks]
    assert len(ids) == len(set(ids)), "v2 task ids must be unique"
    assert len(tasks) >= 24, "pass@1 denominator must be >= 24"
    categories = {"write": 0, "test-fix": 0, "multi-file": 0}
    for task in tasks:
        validate_task(task)
        assert task["grader"]["type"] in GRADER_TYPES
        assert task["max_minutes"] > 0
        categories[task["category"]] = categories.get(task["category"], 0) + 1
    assert categories["write"] >= 8, "need >= 8 real file-write tasks"
    assert categories["test-fix"] >= 4, "need >= 4 run-tests-fix-bug tasks"
    assert categories["multi-file"] >= 4, "need >= 4 multi-file tasks"


def test_v2_report_without_run_is_fully_gradable() -> None:
    report = build_report(v2_tasks(), None)
    assert report["executed_count"] == 0
    assert report["metrics"]["grading_coverage"] == 1.0
    assert report["metrics"]["gradable_task_count"] >= 24
    assert report["metrics"]["pass_at_1"] is None


def test_validate_task_rejects_fixture_path_escape() -> None:
    bad = {
        "id": "escape", "category": "write", "prompt": "x", "max_minutes": 1,
        "fixture": {"../evil.py": "print(1)"},
        "grader": {"type": "file_contract", "files": []},
    }
    with pytest.raises(ValueError, match="逃逸"):
        validate_task(bad)


def test_validate_task_rejects_unknown_grader_type() -> None:
    bad = {
        "id": "g", "category": "write", "prompt": "x", "max_minutes": 1,
        "fixture": {"a.txt": ""},
        "grader": {"type": "magic_oracle"},
    }
    with pytest.raises(ValueError, match="grader"):
        validate_task(bad)


def test_validate_task_rejects_non_positive_max_minutes() -> None:
    bad = {
        "id": "m", "category": "write", "prompt": "x", "max_minutes": 0,
        "fixture": {"a.txt": ""},
        "grader": {"type": "file_contract", "files": []},
    }
    with pytest.raises(ValueError, match="max_minutes"):
        validate_task(bad)


def test_resolve_grader_dir_prefers_explicit_then_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    explicit = tmp_path / "explicit"
    assert resolve_grader_dir(explicit) == explicit.resolve()
    monkeypatch.setenv("MINICC_EVAL_GRADER_DIR", str(tmp_path / "env"))
    assert resolve_grader_dir(None) == (tmp_path / "env").resolve()
    # Default lives OUTSIDE the repository (a sibling .graders), never inside it.
    monkeypatch.delenv("MINICC_EVAL_GRADER_DIR", raising=False)
    default = resolve_grader_dir(None)
    repo_root = Path(bench_tasks.__file__).resolve().parent.parent
    assert default.name == ".graders"
    assert not default.is_relative_to(repo_root)


# ---------------------------------------------------------------------------
# grader discrimination (direct, no model)
# ---------------------------------------------------------------------------


def _write(workspace: Path, files: dict[str, str]) -> None:
    for relative, content in files.items():
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def test_file_contract_passes_and_fails_on_seed_state(tmp_path: Path) -> None:
    tasks = {task["id"]: task for task in v2_tasks()}
    grader_dir = tmp_path / ".graders"

    passing = tmp_path / "pass"
    passing.mkdir()
    _write(passing, tasks["v2-greeting-already-correct"]["fixture"])
    result_pass = grade_v2(tasks["v2-greeting-already-correct"], passing, grader_dir=grader_dir)
    assert result_pass["grader_type"] == "file_contract"
    assert result_pass["passed"] is True

    failing = tmp_path / "fail"
    failing.mkdir()
    _write(failing, tasks["v2-greeting-needs-fix"]["fixture"])
    result_fail = grade_v2(tasks["v2-greeting-needs-fix"], failing, grader_dir=grader_dir)
    assert result_fail["passed"] is False


def test_file_contract_checks_json_and_not_contains(tmp_path: Path) -> None:
    grader_dir = tmp_path / ".graders"
    task = {
        "id": "json", "category": "write", "prompt": "x", "max_minutes": 1,
        "fixture": {"config.json": "{}\n"},
        "grader": {"type": "file_contract", "files": [
            {"path": "config.json", "json_equals": {"a": 1}},
            {"path": "config.json", "not_contains": "TODO"},
        ]},
    }
    ws = tmp_path / "ws"
    ws.mkdir()
    _write(ws, {"config.json": "{}\n"})
    assert grade_v2(task, ws, grader_dir=grader_dir)["passed"] is False
    _write(ws, {"config.json": '{"a": 1}\n'})
    assert grade_v2(task, ws, grader_dir=grader_dir)["passed"] is True


def test_command_contract_discriminates_bug_fix(tmp_path: Path) -> None:
    tasks = {task["id"]: task for task in v2_tasks()}
    task = tasks["v2-fix-add"]
    grader_dir = tmp_path / ".graders"

    # Buggy seed in its own workspace: the test fails.
    buggy = tmp_path / "buggy"
    buggy.mkdir()
    _write(buggy, task["fixture"])
    assert grade_v2(task, buggy, grader_dir=grader_dir)["passed"] is False

    # Fixed source in a separate workspace so a stale __pycache__ from the
    # buggy run (same-mtime bytecode reuse on Windows) cannot mask the fix.
    fixed = tmp_path / "fixed"
    fixed.mkdir()
    _write(fixed, {**task["fixture"], "calc.py": "def add(a, b):\n    return a + b\n"})
    assert grade_v2(task, fixed, grader_dir=grader_dir)["passed"] is True


# ---------------------------------------------------------------------------
# fake-provider end-to-end: one pass, one fail
# ---------------------------------------------------------------------------


def _service_config() -> SimpleNamespace:
    return SimpleNamespace(
        yolo=False, max_concurrent_tasks=2, sandbox_mode="host",
        sandbox_image="python:3.11-slim", base_url="https://example.test/v1",
        api_key="secret", model="test-model", timeout=10, tool_mode="auto",
        reasoning_effort="high", max_turns=4, compact_threshold=300_000,
        context_window_tokens=300_000,
    )


def test_fake_provider_run_yields_one_pass_one_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINICC_FAKE_PROVIDER", "1")
    from minicc.web import AgentService

    original_init = AgentService.__init__

    def patched_init(self, workspace, config, *args, **kwargs):
        original_init(self, workspace, _service_config(), *args, **kwargs)

    monkeypatch.setattr("minicc.web.AgentService.__init__", patched_init)
    monkeypatch.setattr("minicc.config.load_config", _service_config)

    all_tasks = {task["id"]: task for task in v2_tasks()}
    selected = [all_tasks["v2-greeting-already-correct"], all_tasks["v2-greeting-needs-fix"]]
    results = run_benchmark(
        selected, workspace=tmp_path, grader_dir=tmp_path / ".graders",
    )
    by_id = {row["task_id"]: row for row in results}
    # The fake provider never writes, so the seed state decides the verdict:
    # the already-correct fixture passes and the TODO fixture fails. This is
    # the proof the grader is not constant-true.
    assert by_id["v2-greeting-already-correct"]["passed"] is True
    assert by_id["v2-greeting-needs-fix"]["passed"] is False
    assert by_id["v2-greeting-already-correct"]["grader_type"] == "file_contract"


# ---------------------------------------------------------------------------
# hidden grader directory is unreadable by the agent's file tools
# ---------------------------------------------------------------------------


def test_grader_unreadable_by_file_tools(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    (workspace / ".graders").mkdir(parents=True)
    (workspace / ".graders" / "oracle.py").write_text("SECRET = 'answer'\n", encoding="utf-8")
    (workspace / "solution.py").write_text("# work\n", encoding="utf-8")
    registry = build_registry(Editor(workspace))

    calls = [
        ToolCall("read_file", {"path": ".graders/oracle.py"}),
        ToolCall("grep", {"pattern": "SECRET", "path": ".graders"}),
        ToolCall("glob", {"pattern": "*", "path": ".graders"}),
        ToolCall("tree", {"path": ".graders"}),
    ]
    for call in calls:
        result = registry.execute(call)
        assert result.status == "error", f"{call.name} should error on .graders"
        assert "TOOL_ERROR" in result.summary, f"{call.name}: {result.summary}"


def test_graders_hidden_from_recursive_discovery(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    (workspace / ".graders").mkdir(parents=True)
    (workspace / ".graders" / "oracle.py").write_text("SECRET = 'answer'\n", encoding="utf-8")
    (workspace / "solution.py").write_text("# work\n", encoding="utf-8")
    registry = build_registry(Editor(workspace))
    # A workspace-wide tree/glob/grep must not reveal the grader directory.
    tree = registry.execute(ToolCall("tree", {}))
    assert ".graders" not in tree.render()
    glob = registry.execute(ToolCall("glob", {"pattern": "**/*.py"}))
    assert ".graders" not in glob.render()
    grep = registry.execute(ToolCall("grep", {"pattern": "SECRET"}))
    # The summary echoes the pattern itself, so assert on the match body: the
    # grader file must never appear as a hit.
    assert ".graders" not in grep.render()
    assert "oracle.py" not in grep.render()
    assert "(无匹配)" in grep.render()
