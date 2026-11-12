"""M8-T89: one column, one declared vocabulary, one derivation.

Three places fill the ``grader_type`` column and each used to spell its own
value. Measured before this batch - same task file, same answer, only the run
outcome changed:

| declared grader | row when the run completed | row when it was cancelled |
| --- | --- | --- |
| no ``type`` | ``ungraded`` | ``behavior`` |
| ``type: weird_thing`` | ``ungraded`` | ``weird_thing`` |
| ``type: python_behavior``, ``cases: None`` | ``behavior`` + REFUSED | ``python_behavior`` |

So the label depended on whether the run finished, and one value (``behavior``)
names a *suite* rather than any grader the repo answers with - the invented
label shape M8-T83 retired as ``invalid``, left standing in the cancelled
branch. The caliber here: **the column names the grader that judged the row, or
the one that would have, and the names are declared once.**

Two censuses hold the column to that. One compares the literal set against the
vocabulary for *equality*, so an invented label and a dead vocabulary entry both
fail. The other forbids a writer from re-deriving the label inline (reading the
task's own ``type`` key, which is how the ``behavior`` default got in). Both
read values written *under the column key*, so a label that reaches the column
through a local variable is invisible to them by construction; that shape is
left to the behavioural arms above.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import minicc.bench_tasks as bench_tasks
from minicc.benchmarks import build_report, run_benchmark

REPO_ROOT = Path(__file__).resolve().parent.parent
VOCABULARY = set(bench_tasks.GRADER_TYPE_VOCABULARY)

# (label, grader spec). One entry per dispatch decision, so a fix that only
# covers the type it happened to be shown does not pass.
SPECS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("no type", {"cases": []}),
    ("unknown type", {"type": "weird_thing"}),
    ("behavior type", {"type": "python_behavior", "cases": []}),
    ("answer rubric", {"type": "answer_rubric", "required_any": [["a"]]}),
    ("v2 file contract", {"type": "file_contract", "files": []}),
    ("v2 command contract", {"type": "command_contract", "command": "exit 0"}),
)


def _service_config() -> SimpleNamespace:
    return SimpleNamespace(
        yolo=False, max_concurrent_tasks=2, sandbox_mode="host",
        sandbox_image="python:3.11-slim", base_url="https://example.test/v1",
        api_key="test-key", model="test-model", temperature=0.0, max_tokens=100,
        request_timeout=30, system_prompt=None, task_store_path=None,
        sampling_enabled=False,
    )


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, task: dict[str, Any],
         outcome: dict[str, Any]) -> dict[str, Any]:
    class Service:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def _chat_locked(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            return outcome

        def shutdown(self) -> None:
            pass

    monkeypatch.setattr("minicc.web.AgentService", Service)
    monkeypatch.setattr("minicc.config.load_config", _service_config)
    # Keep the materialized grader scripts inside the test tree: the default
    # lives beside the repository, and a gate should not write there.
    rows = run_benchmark([task], workspace=tmp_path, grader_dir=tmp_path / "graders")
    return rows[0]


# --- the defect: the label moved when the run did not finish -----------------


@pytest.mark.parametrize("label,grader", SPECS, ids=[entry[0] for entry in SPECS])
def test_the_label_does_not_depend_on_whether_the_run_finished(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, label: str, grader: dict[str, Any]
) -> None:
    """Same file, two outcomes, one label - and it is a declared one."""
    task = {"id": "case", "prompt": "x", "grader": grader}
    expected = bench_tasks.declared_grader_type(task)
    assert expected in VOCABULARY, expected
    completed = _run(tmp_path, monkeypatch, task, {"answer": "a"})
    cancelled = _run(tmp_path, monkeypatch, task, {"answer": "a", "cancelled": True})
    assert completed["grader_type"] == expected, (label, completed)
    assert cancelled["grader_type"] == expected, (label, cancelled)
    assert cancelled["grader_type"] in VOCABULARY, (label, cancelled)


def test_a_grader_that_blew_up_is_labelled_by_the_type_it_declared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``behavior`` named the suite in a row whose real grader was python_behavior."""
    task = {"id": "case", "prompt": "x", "grader": {"type": "python_behavior", "cases": None}}
    row = _run(tmp_path, monkeypatch, task, {"answer": "a"})
    assert row["grading_refused"] is True, row
    assert row["passed"] is None, row
    assert row["grader_type"] == "python_behavior", row
    assert "TypeError" in row["refusal"], row


def test_the_legacy_command_grader_keeps_its_own_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``command`` is the one label that is not a declared ``grader.type``."""
    task = {"id": "case", "prompt": "x", "verify_command": "exit 0"}
    assert _run(tmp_path, monkeypatch, task, {"answer": "a"})["grader_type"] == "command"
    cancelled = _run(tmp_path, monkeypatch, task, {"answer": "a", "cancelled": True})
    assert cancelled["grader_type"] == "command"


def test_a_report_row_with_no_recorded_result_uses_the_same_rule() -> None:
    """The third site: a task whose row was never written still names its grader."""
    tasks = [
        {"id": "v2", "prompt": "x", "grader": {"type": "file_contract", "files": []}},
        {"id": "bare", "prompt": "x"},
        {"id": "legacy", "prompt": "x", "verify_command": "exit 0"},
        {"id": "unknown", "prompt": "x", "grader": {"type": "weird_thing"}},
    ]
    labels = {row["task_id"]: row["grader_type"] for row in build_report(tasks, [])["results"]}
    assert labels == {
        "v2": "file_contract", "bare": "ungraded", "legacy": "command", "unknown": "ungraded",
    }, labels
    assert set(labels.values()) <= VOCABULARY, labels


# --- census: the literal set is the vocabulary, both ways ------------------


def _production_sources() -> list[tuple[str, ast.Module]]:
    out: list[tuple[str, ast.Module]] = []
    for path in sorted((REPO_ROOT / "minicc").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        out.append((path.relative_to(REPO_ROOT).as_posix(),
                    ast.parse(path.read_text(encoding="utf-8"))))
    return out


def _grader_type_writes(node: ast.AST) -> list[tuple[str, ast.expr]]:
    """(key, value) pairs this node may fill the column from.

    A row gets a label three ways: a dict literal, a keyword argument, a
    subscript assignment - plus the default handed to ``.get("grader_type", x)``,
    the value the column takes when the row recorded none (the old
    ``build_report`` line reached the column exactly that way).
    """
    pairs: list[tuple[str | None, ast.expr | None]] = []
    if isinstance(node, ast.Dict):
        pairs = [(k.value if isinstance(k, ast.Constant) else None, v)
                 for k, v in zip(node.keys, node.values)]
    elif isinstance(node, ast.Call):
        pairs = [(k.arg, k.value) for k in node.keywords]
        if (isinstance(node.func, ast.Attribute) and node.func.attr == "get"
                and len(node.args) >= 2 and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "grader_type"):
            pairs.append(("grader_type", node.args[1]))
    elif isinstance(node, ast.Assign):
        pairs = [((target.slice.value if isinstance(target.slice, ast.Constant) else None),
                  node.value)
                 for target in node.targets if isinstance(target, ast.Subscript)]
    return [(key, value) for key, value in pairs
            if key == "grader_type" and value is not None]


def _writes_under_grader_type(
    sources: list[tuple[str, ast.Module]]
) -> list[tuple[str, ast.expr]]:
    return [(name, value) for name, tree in sources
            for node in ast.walk(tree) for _key, value in _grader_type_writes(node)]


def _literal_grader_types(sources: list[tuple[str, ast.Module]]) -> set[str]:
    return {value.value for _name, value in _writes_under_grader_type(sources)
            if isinstance(value, ast.Constant) and isinstance(value.value, str)}


def test_the_column_speaks_only_the_declared_vocabulary() -> None:
    """Equality both ways: no invented label, no dead vocabulary entry."""
    written = _literal_grader_types(_production_sources())
    assert written == VOCABULARY, (
        f"invented label(s): {sorted(written - VOCABULARY)}; "
        f"declared but never written: {sorted(VOCABULARY - written)}"
    )
    assert len(VOCABULARY) >= 6, f"the vocabulary went blind: {sorted(VOCABULARY)}"


def test_no_writer_re_derives_the_label_from_the_task_file() -> None:
    """The column is filled by one derivation, not by reading ``grader.type``.

    This is the shape the literal census cannot see: a fresh default like
    ``task["grader"].get("type", "behavior")`` never appears under the column
    key, yet it is what the row ends up carrying.
    """
    inline = [name for name, value in _writes_under_grader_type(_production_sources())
              for node in ast.walk(value)
              if isinstance(node, ast.Constant) and node.value == "type"]
    assert inline == [], (
        f"these writers re-derive the grader label instead of deriving it once: {inline}")


def test_the_vocabulary_census_sees_a_planted_label() -> None:
    """Reverse control: each write shape must be visible, prose must not be."""
    plants = [
        "def f(e):\n    e.update(grader_type=\"behavior\")\n",
        "def f(e):\n    return {\"grader_type\": \"behavior\"}\n",
        "def f(e):\n    e[\"grader_type\"] = \"behavior\"\n",
        "def f(row):\n    return row.get(\"grader_type\", \"behavior\")\n",
    ]
    seen = _literal_grader_types([(f"plant{i}", ast.parse(src))
                                  for i, src in enumerate(plants)])
    assert seen == {"behavior"}, seen
    assert seen - VOCABULARY == {"behavior"}
    variable = "def f(e, label):\n    e.update(grader_type=label)\n"
    assert _literal_grader_types([("variable", ast.parse(variable))]) == set()
    prose = "# grader_type = behavior, in a comment\n"
    assert _literal_grader_types([("prose", ast.parse(prose))]) == set()


def test_the_inline_census_sees_the_planted_default() -> None:
    """Reverse control for the rule above, including its blind spot."""
    planted = ("def f(e, task):\n"
               "    e.update(grader_type=task[\"grader\"].get(\"type\", \"behavior\"))\n")
    writes = _writes_under_grader_type([("plant", ast.parse(planted))])
    assert [name for name, _value in writes] == ["plant"], writes
    constants = [node.value for _name, value in writes
                 for node in ast.walk(value) if isinstance(node, ast.Constant)]
    assert "type" in constants, constants
    derived = ("def f(e, task):\n"
               "    e.update(grader_type=declared(task))\n")
    assert [node.value for _n, value in _writes_under_grader_type([("ok", ast.parse(derived))])
            for node in ast.walk(value) if isinstance(node, ast.Constant)] == []
