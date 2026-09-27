"""M8-T83: a grader nobody could run must not be charged to the agent.

M8-T80 gave the exit-2 refusal a NO-RESULT channel and M8-T81 taught the report
to read it. Three shapes still bypassed that channel (measured on ``e4a648b``):

* ``grade_file_contract`` / ``grade_command_contract`` turned ``OSError`` and
  their own wall-clock timeout into ``passed=False`` plus an ``error`` key -
  which also overwrote the agent's own ``error`` string in the result row,
  because the runner writes that field first and then ``entry.update``\\ s the
  grader dict over it;
* the runner's wrapper recorded ``grader_type="invalid"`` with a
  ``grading_error`` field that had one writer and zero readers, in code, tests
  and docs alike, and that branch had no test case at all.

A workspace the grader never looked at is neither a pass nor a failure. The
controls below keep that from becoming a way to make red disappear.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import minicc.bench_tasks as bench_tasks
import minicc.benchmarks as benchmarks
from minicc.benchmarks import build_report, markdown_report, run_benchmark

REPO_ROOT = Path(__file__).resolve().parent.parent
NO_RESULT_KEYS = {"passed", "grader_type", "grading_refused", "refusal"}


def _file_task(**spec_extra: object) -> dict[str, object]:
    return {"id": "t", "grader": {"type": "file_contract", "files": [], **spec_extra}}


def _command_task() -> dict[str, object]:
    return {"id": "t", "grader": {"type": "command_contract", "command": "python x.py"}}


@pytest.mark.parametrize("grader_name,task", [
    ("grade_file_contract", _file_task(files=[{"path": "a.txt", "exists": True}])),
    ("grade_command_contract", _command_task()),
])
@pytest.mark.parametrize("exc", [
    OSError(13, "Permission denied"),
    subprocess.TimeoutExpired(cmd="grader", timeout=1),
])
def test_a_grader_the_host_could_not_run_is_no_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, grader_name: str,
    task: dict[str, object], exc: BaseException,
) -> None:
    """The workspace was never examined, so there is no verdict to report."""

    def unable(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise exc

    monkeypatch.setattr(bench_tasks, "_run_grader", unable)
    graded = getattr(bench_tasks, grader_name)(task, tmp_path, grader_dir=tmp_path / "graders")
    assert graded["passed"] is None, f"a host failure was graded as the agent's failure: {graded}"
    assert graded["grading_refused"] is True
    assert type(exc).__name__ in graded["refusal"], graded
    assert graded["grader_type"] == task["grader"]["type"]


@pytest.mark.parametrize("grader_name", ["grade_file_contract", "grade_command_contract"])
def test_an_unrunnable_grader_stops_writing_the_key_that_shadowed_the_agent_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, grader_name: str
) -> None:
    """``error`` carried the exception name and the agent's own error string.

    The runner sets ``entry["error"]`` from the outcome and then updates the row
    with the grader dict, so a grader ``error`` key silently replaced the one
    diagnostic the agent produced. ``refusal`` is the field with readers.
    """
    def unable(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError("cannot start")

    monkeypatch.setattr(bench_tasks, "_run_grader", unable)
    graded = getattr(bench_tasks, grader_name)(
        _file_task(), tmp_path, grader_dir=tmp_path / "graders")
    assert "error" not in graded, graded
    assert set(graded) == NO_RESULT_KEYS, graded


def test_both_no_result_shapes_agree_on_the_shared_keys(tmp_path: Path) -> None:
    """One verdict, two entrances: the dicts must not drift apart."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "notes.txt").write_bytes("评分标记".encode("gbk"))
    refused = bench_tasks.grade_file_contract(
        {"grader": {"type": "file_contract",
                    "files": [{"path": "notes.txt", "not_contains": "评分标记"}]}},
        workspace, grader_dir=tmp_path / "graders")
    unable = bench_tasks.grader_unable("file_contract", OSError("cannot start"))
    assert refused["passed"] is unable["passed"] is None
    assert refused["grading_refused"] is unable["grading_refused"] is True
    assert set(refused) == NO_RESULT_KEYS | {"exit_code", "case_count"}, refused
    assert set(unable) == NO_RESULT_KEYS, unable


def test_a_real_pass_and_a_real_failure_stay_verdicts(tmp_path: Path) -> None:
    """The channel must not swallow work that was actually judged."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "report.md").write_text("# 报告\n评分标记\n", encoding="utf-8")
    ok = bench_tasks.grade_file_contract(
        {"grader": {"type": "file_contract",
                    "files": [{"path": "report.md", "contains": "评分标记"}]}},
        workspace, grader_dir=tmp_path / "graders")
    assert ok["passed"] is True, ok
    bad = bench_tasks.grade_file_contract(
        {"grader": {"type": "file_contract",
                    "files": [{"path": "report.md", "contains": " absent "}]}},
        workspace, grader_dir=tmp_path / "graders")
    assert bad["passed"] is False, bad
    for graded in (ok, bad):
        assert "grading_refused" not in graded


# --- the runner's own wrapper: the branch that had no test case at all ------


class _Service:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def _chat_locked(self, payload: dict[str, object], **kwargs: object) -> dict[str, object]:
        return {"answer": "done", "turns": 2, "tool_calls_total": 1, "events": []}

    def shutdown(self) -> None:
        pass


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        yolo=True, max_concurrent_tasks=1, sandbox_mode="host",
        sandbox_image="python:3.11-slim", base_url="https://example.test/v1",
        api_key="test-key", model="test-model", timeout=10, tool_mode="auto",
        reasoning_effort="high", max_turns=4, compact_threshold=300_000,
        context_window_tokens=300_000,
    )


def _task_with_a_broken_grader() -> dict[str, object]:
    """A grader spec the host itself cannot honour.

    ``timeout`` is read with ``float()`` inside the grader's own ``try``, so it
    escapes as ValueError - past the grader, into the runner's wrapper. The
    spec stays JSON-serialisable, so ``fixture_digest`` lets the task through
    and the row still has to say "nobody judged this".
    """
    return {"id": "bad-spec", "prompt": "改 LICENSE", "category": "write",
            "grader": {"type": "file_contract", "files": [{"path": "LICENSE", "exists": True}],
                       "timeout": "60s"}}


def test_a_grader_spec_the_host_cannot_hand_over_is_recorded_as_a_refusal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """End to end: a ValueError out of the grader reaches the row as None."""
    monkeypatch.setattr("minicc.web.AgentService", _Service)
    monkeypatch.setattr("minicc.config.load_config", _config)
    row = run_benchmark([_task_with_a_broken_grader()], workspace=tmp_path)[0]
    assert row["status"] == "completed", row
    assert row["passed"] is None, row
    assert row["grading_refused"] is True, row
    assert row["grader_type"] == "file_contract", row
    assert "ValueError" in str(row["refusal"]), row
    assert "grading_error" not in row, row


def test_the_refusal_from_a_broken_grader_is_readable_in_the_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("minicc.web.AgentService", _Service)
    monkeypatch.setattr("minicc.config.load_config", _config)
    task = _task_with_a_broken_grader()
    rows = run_benchmark([task], workspace=tmp_path)
    report = build_report([task], rows)
    assert report["metrics"]["grading_refusal_count"] == 1, report["metrics"]
    assert report["metrics"]["gradable_task_count"] == 0, report["metrics"]
    text = markdown_report(report)
    line = next(line for line in text.splitlines() if "bad-spec" in line and line.startswith("|"))
    assert "REFUSED" in line and "ValueError" in line, line


def test_the_report_still_explains_both_entrances_to_one_verdict() -> None:
    """A note naming only exit 2 would misdescribe every host-side refusal."""
    note = next(line for line in build_report([], [])["notes"] if line.startswith("REFUSED"))
    assert "exit 2" in note, note
    assert "could not be run" in note, note


# --- census: keep the retired fields and the shared shape honest -----------


def _production_sources() -> list[tuple[str, ast.Module]]:
    out: list[tuple[str, ast.Module]] = []
    for path in sorted((REPO_ROOT / "minicc").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        out.append((path.relative_to(REPO_ROOT).as_posix(),
                    ast.parse(path.read_text(encoding="utf-8"))))
    return out


def _written_names(node: ast.AST) -> list[tuple[str | None, ast.expr | None]]:
    """(name, value) pairs a node writes: dict literal keys and keyword arguments."""
    if isinstance(node, ast.Dict):
        return [(k.value if isinstance(k, ast.Constant) else None, v)
                for k, v in zip(node.keys, node.values)]
    if isinstance(node, ast.Call):
        return [(k.arg, k.value) for k in node.keywords]
    return []


def _literal_key_writers(sources: list[tuple[str, ast.Module]], key: str) -> list[str]:
    """Modules that write ``key`` into a dict literal or as a keyword argument."""
    return [name for name, tree in sources
            if any(kw == key for node in ast.walk(tree) for kw, _ in _written_names(node))]


def _true_flag_writers(sources: list[tuple[str, ast.Module]], key: str) -> dict[str, int]:
    """Per-module count of literal ``True`` written under ``key``.

    Naming the key is not constructing a refusal: ``build_report`` reads it with
    ``bool(recorded.get(...))`` (M8-T81's reader) and must not be counted here,
    or the gate would fight the report for mentioning the field it displays.
    """
    tally: dict[str, int] = {}
    for name, tree in sources:
        hits = sum(1 for node in ast.walk(tree)
                   for kw, value in _written_names(node)
                   if kw == key and isinstance(value, ast.Constant) and value.value is True)
        if hits:
            tally[name] = tally.get(name, 0) + hits
    return tally


def test_the_no_result_shape_is_constructed_in_exactly_one_place() -> None:
    """A second ``True`` literal is where the two entrances drift apart again."""
    sources = _production_sources()
    tally = _true_flag_writers(sources, "grading_refused")
    assert tally == {"minicc/bench_tasks.py": 1}, tally


def _literal_values_for_key(sources: list[tuple[str, ast.Module]], key: str) -> set[object]:
    """Constants written under ``key`` in a dict literal or as a keyword argument."""
    return {value.value for _, tree in sources
            for node in ast.walk(tree) for kw, value in _written_names(node)
            if kw == key and isinstance(value, ast.Constant)}


def test_grading_error_has_no_writer_left() -> None:
    assert _literal_key_writers(_production_sources(), "grading_error") == [], \
        "the unread field came back"


def test_the_invented_grader_type_string_has_no_writer_left() -> None:
    """``"invalid"`` named the host's bug in the column that names the grader."""
    written = _literal_values_for_key(_production_sources(), "grader_type")
    assert "invalid" not in written, sorted(str(item) for item in written)
    assert "file_contract" in written, "the census is not reading the graders at all"


def test_the_census_counts_a_planted_writer_so_a_return_cannot_be_hollow() -> None:
    """Reverse control for the gates above, run on strings rather than the tree."""
    planted_dict = "def f():\n    return {'passed': False, 'grading_error': 'x'}\n"
    planted_kwarg = "def f(e):\n    e.update(grader_type='invalid')\n"
    assert _literal_key_writers([("dict", ast.parse(planted_dict))], "grading_error") == ["dict"]
    assert "invalid" in _literal_values_for_key(
        [("kwarg", ast.parse(planted_kwarg))], "grader_type")
    second_constructor = "def g(t):\n    return {'passed': None, 'grading_refused': True}\n"
    assert _true_flag_writers([("second", ast.parse(second_constructor))],
                             "grading_refused") == {"second": 1}, \
        "a hand-copied refusal row would slip past the one-constructor gate"
    reader_only = "def r(row):\n    return bool(row.get('grading_refused'))\n"
    assert _true_flag_writers([("reader", ast.parse(reader_only))], "grading_refused") == {}
    assert _literal_key_writers([("prose", ast.parse("# grading_error in a comment\n"))],
                               "grading_error") == []
