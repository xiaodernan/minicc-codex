"""M8-T379 — 任务的 stream_length 只有一个含义：累计总量

summary() 与 snapshot() 同一个键（stream_length）同一个对象必须给出同一个值。

M8-T531 re-fitted the structural half of this file: the source is read with the
handle closed, the source is parsed **once**, and a fall-through names the thing
that is actually missing instead of reporting that ``summary()`` is gone when it
is standing right there.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from minicc.task_manager import TaskRecord

#: Anchored on this file, not on the working directory: a gate that only runs
#: from one cwd reports a missing file when the cwd is different.
TASK_MANAGER_SOURCE = Path(__file__).resolve().parents[1] / "minicc" / "task_manager.py"


def test_the_task_stream_length_has_one_meaning() -> None:
    """summary() 与 snapshot() 报出的 stream_length 必须一致。

    语义统一为"累计总量"（self.stream_length），而不是"截断后的尾部长度"。
    """
    record = TaskRecord(
        task_id="t1",
        session_id="s1",
        message="hello",
        allow_changes=False,
        stream_limit=16000,
    )
    for _ in range(400):
        record.append_stream("x" * 100)

    summary = record.summary()
    snapshot = record.snapshot()

    assert summary["stream_length"] == snapshot["stream_length"], (
        f"summary.stream_length ({summary['stream_length']}) != "
        f"snapshot.stream_length ({snapshot['stream_length']}); "
        "the same key must have the same meaning on both faces"
    )
    # The shared value must be the total streamed, not the tail length
    assert summary["stream_length"] > 16000, (
        "stream_length must be the total streamed (accumulated), "
        f"not the truncated tail ({summary['stream_length']})"
    )


def test_the_summary_has_no_stream_total_length() -> None:
    """summary() 不再有 stream_total_length（它就是 stream_length）。"""
    record = TaskRecord(
        task_id="t1",
        session_id="s1",
        message="hello",
        allow_changes=False,
    )
    record.append_stream("x" * 100)
    summary = record.summary()
    assert "stream_total_length" not in summary, (
        "summary must not contain stream_total_length; "
        "stream_length is the single total"
    )


def test_the_summary_reports_tail_length_separately() -> None:
    """summary() 单独报告 tail 长度（当前保留的字符数）。"""
    record = TaskRecord(
        task_id="t1",
        session_id="s1",
        message="hello",
        allow_changes=False,
        stream_limit=16000,
    )
    for _ in range(400):
        record.append_stream("x" * 100)

    summary = record.summary()
    assert summary["stream_tail_length"] == 16000, (
        f"stream_tail_length should be the tail limit (16000), "
        f"got {summary['stream_tail_length']}"
    )
    assert summary["stream_length"] == 40000, (
        "stream_length is the total streamed, not the tail"
    )


def _summary_method(tree: ast.AST, *, where: str = TASK_MANAGER_SOURCE.name) -> ast.FunctionDef:
    """The module's one ``summary()``, or a sentence naming what is missing.

    Two methods with the name is its own failure: whichever the walk reaches
    first is not necessarily the one the gate then reports on.
    """
    summaries = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "summary"]
    if not summaries:
        raise AssertionError(f"{where} defines no summary() method at all")
    if len(summaries) > 1:
        raise AssertionError(
            f"{where} defines summary() {len(summaries)} times "
            f"(lines {[node.lineno for node in summaries]}); this gate cannot say "
            "which one carries the key, so it would read one method and report on another"
        )
    return summaries[0]


def _stream_length_value(summary: ast.FunctionDef) -> ast.expr:
    """What ``summary()`` puts under ``"stream_length"``, or what is really absent."""
    for node in ast.walk(summary):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value == "stream_length":
                return value
    raise AssertionError(
        f"summary() (line {summary.lineno}) builds no dict entry keyed "
        "'stream_length' - the method is there; the key is what is missing"
    )


def test_the_stream_length_is_the_same_object() -> None:
    """The value comes from the same field (structural assertion)."""
    source = TASK_MANAGER_SOURCE.read_text(encoding="utf-8")
    value = _stream_length_value(_summary_method(ast.parse(source)))
    # Must be an Attribute (self.stream_length)
    assert isinstance(value, ast.Attribute), (
        "summary()['stream_length'] must be self.stream_length "
        "(the accumulated total), not len(self.stream_text)"
    )
    assert value.attr == "stream_length", "summary() must use self.stream_length"


def test_the_structural_read_still_finds_its_source_from_another_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The read is anchored on this file, so a different cwd cannot empty it.

    The shipped form was ``open("minicc/task_manager.py")``: from any directory
    but the repo root that reports the source as missing, and a gate that
    cannot find its subject says nothing about it.
    """
    monkeypatch.chdir(tmp_path)
    try:
        source = TASK_MANAGER_SOURCE.read_text(encoding="utf-8")
    except OSError as exc:
        raise AssertionError(
            f"the structural read could not find its source from cwd={tmp_path}: "
            f"{TASK_MANAGER_SOURCE} ({exc}); a gate anchored on the working "
            "directory reports the subject as missing whenever pytest starts "
            "anywhere else"
        ) from exc
    assert "def summary(" in source, (
        f"the structural read found no summary() in {TASK_MANAGER_SOURCE} while cwd={tmp_path}"
    )


def test_two_summary_methods_are_not_silently_picked_one_of(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ambiguity is reported, not resolved by walk order.

    ``ast.walk`` reaches one of them first and the gate would then report on
    whichever it happened to meet - which is the same wrong-side diagnosis as
    the fall-through, wearing a green badge.
    """
    two = ast.parse(
        "class A:\n    def summary(self):\n        return {'stream_length': self.stream_length}\n"
        "class B:\n    def summary(self):\n        return {'stream_length': 1}\n"
    )
    with pytest.raises(AssertionError) as raised:
        _summary_method(two, where="synthetic module")
    message = str(raised.value)
    assert "2 times" in message and "lines [2, 5]" in message, message


def test_a_missing_key_is_not_reported_as_a_missing_method() -> None:
    """Two different failures get two different sentences.

    The shipped gate ended in one ``raise`` covering both "there is no
    ``summary()``" and "``summary()`` has no such key", so renaming the key
    reported that the method was gone. A diagnosis that blames the wrong side
    trains the next reader to delete the correct claim.
    """
    no_method = ast.parse("class TaskRecord:\n    def snapshot(self):\n        return {}\n")
    with pytest.raises(AssertionError) as method_missing:
        _summary_method(no_method)
    assert "no summary() method" in str(method_missing.value), str(method_missing.value)

    key_gone = ast.parse("class TaskRecord:\n    def summary(self):\n        return {'stream_tail_length': 1}\n")
    with pytest.raises(AssertionError) as key_missing:
        _stream_length_value(_summary_method(key_gone))
    message = str(key_missing.value)
    assert "stream_length" in message and "the method is there" in message, message
    assert "no summary() method" not in message, (
        f"both failures are being reported with the same sentence: {message}"
    )
