"""M8-T438 — 上下文发布载荷两键两个家：替换写入与合并写入各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/task_manager.py"

FIELDS = {"context", "state_version"}


def _record(**fields: object) -> object:
    from minicc.task_manager import TaskRecord

    record = TaskRecord.__new__(TaskRecord)
    for name, value in fields.items():
        setattr(record, name, value)
    return record


def test_the_home_builds_the_payload() -> None:
    """The constructor owns the pair; the context is a copy, not the live dict."""
    record = _record(context={"a": 1}, state_version=3)
    payload = record._context_payload_locked()
    assert payload == {"context": {"a": 1}, "state_version": 3}
    payload["context"]["a"] = 2
    assert record.context == {"a": 1}


def test_the_two_keys_are_spelled_exactly_once_in_the_package() -> None:
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
        "the context publish payload is spelled by hand outside its "
        "one home: " + ", ".join(offenders)
    )


def test_both_writers_ask_the_home() -> None:
    """The replacing writer, the merging writer, and the definition itself."""
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("_context_payload_locked(") == 3, (
        "the definition plus the two writers are the only spellings, "
        f"found {source.count('_context_payload_locked(')}"
    )
