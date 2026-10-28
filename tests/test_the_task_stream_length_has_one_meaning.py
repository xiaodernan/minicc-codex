"""M8-T379 — 任务的 stream_length 只有一个含义：累计总量

summary() 与 snapshot() 同一个键（stream_length）同一个对象必须给出同一个值。
"""

from __future__ import annotations

from pathlib import Path

from minicc.task_manager import TaskRecord

_TASK_MANAGER = Path(__file__).resolve().parent.parent / "minicc" / "task_manager.py"


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


def test_the_stream_length_is_the_same_object() -> None:
    """The value comes from the same field (structural assertion)."""
    import ast
    tree = ast.parse(_TASK_MANAGER.read_text(encoding="utf-8"))
    # Find summary() method
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "summary":
            # Find the stream_length assignment in the returned dict
            for n in ast.walk(node):
                if isinstance(n, ast.Dict):
                    for i, key in enumerate(n.keys):
                        if isinstance(key, ast.Constant) and key.value == "stream_length":
                            val = n.values[i]
                            # Must be an Attribute (self.stream_length)
                            assert isinstance(val, ast.Attribute), (
                                "summary()['stream_length'] must be self.stream_length "
                                "(the accumulated total), not len(self.stream_text)"
                            )
                            assert val.attr == "stream_length", (
                                "summary() must use self.stream_length"
                            )
                            return
    raise AssertionError("summary() method not found")