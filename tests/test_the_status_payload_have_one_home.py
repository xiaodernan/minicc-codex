"""M8-T437 — 任务状态发布载荷六键两个家：通用转移与取消请求各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/task_manager.py"

FIELDS = {
    "cancel_reason", "error", "finished_at",
    "phase", "state_version", "status",
}


def _record(**fields: object) -> object:
    from minicc.task_manager import TaskRecord

    record = TaskRecord.__new__(TaskRecord)
    for name, value in fields.items():
        setattr(record, name, value)
    return record


def test_the_home_builds_the_payload() -> None:
    """The constructor owns the six keys and the finished_at formatting."""
    record = _record(
        status="cancelled",
        phase="cancelled",
        state_version=7,
        finished_at=0.0,
        error="任务已取消",
        cancel_reason="user",
    )
    payload = record._status_payload_locked()
    assert set(payload) == FIELDS
    assert payload["status"] == "cancelled"
    assert payload["state_version"] == 7
    assert payload["error"] == "任务已取消"
    assert payload["cancel_reason"] == "user"
    assert payload["finished_at"] is not None


def test_the_six_keys_are_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second publish shape."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = {
                key.value
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            if keys == FIELDS:
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the task status publish payload is spelled by hand outside its "
        "one home: " + ", ".join(offenders)
    )


def test_both_transitions_ask_the_home() -> None:
    """The lifecycle transition, the cancel request, and the definition."""
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("_status_payload_locked(") == 3, (
        "the definition plus the two publishes are the only spellings, "
        f"found {source.count('_status_payload_locked(')}"
    )
