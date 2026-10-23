"""M8-T391 — worker 元数据四字段：镜像写出与恢复读回两个家"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/task_execution.py"

FIELDS = frozenset({"worker_version", "worker_pid", "lease_owner", "heartbeat_at_epoch"})


def test_the_home_exists_in_task_execution() -> None:
    """task_execution.py owns the four fields, in one canonical order."""
    from minicc.task_execution import WORKER_METADATA_FIELDS

    assert WORKER_METADATA_FIELDS == (
        "worker_version", "worker_pid", "lease_owner", "heartbeat_at_epoch",
    )


def test_task_manager_asks_the_home() -> None:
    """task_manager.py uses the same object, not its own spelling."""
    import minicc.task_execution as task_execution
    import minicc.task_manager as task_manager

    assert task_manager.WORKER_METADATA_FIELDS is task_execution.WORKER_METADATA_FIELDS


def test_no_module_inlines_the_fields() -> None:
    """No module spells the four fields as a literal outside the one declaration."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Set | ast.Tuple | ast.List):
                continue
            elements = frozenset(
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
            if len(node.elts) >= 2 and elements == FIELDS:
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the worker metadata fields are spelled inline outside the one declaration: "
        + ", ".join(offenders)
    )


def test_the_mirror_still_carries_the_fields() -> None:
    """The snapshot mirror still copies exactly those fields onto the task."""

    class _Task:
        stream_length = 0
        compaction_events: list = []

        def set_phase(self, phase): self.phase = phase
        def add_compaction(self, event): pass
        def update_usage(self, usage, cumulative=False): pass
        def update_context(self, context): pass

    from minicc.task_execution import WorkerSnapshotMirror

    task = _Task()
    task.worker_metadata = {}
    mirror = WorkerSnapshotMirror(task)
    snapshot = {
        "worker_version": "1.2.3",
        "worker_pid": 4242,
        "lease_owner": "worker-1",
        "heartbeat_at_epoch": 123.5,
        "unrelated_field": "ignored",
    }
    mirror.apply(snapshot)
    assert task.worker_metadata == {
        "worker_version": "1.2.3",
        "worker_pid": 4242,
        "lease_owner": "worker-1",
        "heartbeat_at_epoch": 123.5,
    }
