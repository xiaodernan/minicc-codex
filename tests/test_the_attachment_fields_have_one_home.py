"""M8-T392 — 附件四字段：snapshot() 与 summary() 两个序列化各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/task_manager.py"

FIELDS = frozenset({"name", "mime_type", "size_bytes", "path"})


def test_the_home_exists_in_task_manager() -> None:
    """task_manager.py owns the four attachment fields."""
    from minicc.task_manager import ATTACHMENT_FIELDS

    assert ATTACHMENT_FIELDS == ("name", "mime_type", "size_bytes", "path")


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
        "the attachment fields are spelled inline outside the one declaration: "
        + ", ".join(offenders)
    )


def test_both_serializers_agree() -> None:
    """snapshot() and summary() carry the same attachment shape."""
    from minicc.task_manager import TaskRecord

    task = TaskRecord(
        task_id="t1",
        session_id="s1",
        message="p",
        allow_changes=False,
        attachments=[
        {"name": "a.png", "mime_type": "image/png", "size_bytes": 10, "path": ".minicc/attachments/a.png"},
        {"name": "b.png"},
    ])
    snapshot_attachments = task.snapshot()["attachments"]
    summary_attachments = task.summary()["attachments"]
    assert snapshot_attachments == summary_attachments
    assert snapshot_attachments[0] == {
        "name": "a.png",
        "mime_type": "image/png",
        "size_bytes": 10,
        "path": ".minicc/attachments/a.png",
    }
    assert snapshot_attachments[1] == {"name": "b.png"}
