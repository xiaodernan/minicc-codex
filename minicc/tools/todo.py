"""TodoWrite-equivalent tool: the model's shared task checklist.

Claude Code exposes a TodoWrite tool so the model can publish a plan the UI
renders as a live checklist. Here the checklist is persisted under
``<workspace>/.minicc/todos.json`` (atomic replace) and returned as structured
``ToolResult.data`` so web task events can carry it to the frontend panel.

The tool maps to ``readonly`` risk on purpose: it only writes agent-internal
state inside ``.minicc/``, never user code, so no confirmation dialog is
required.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from .registry import ToolResult

TODO_STATUSES = ("pending", "in_progress", "completed")
TODO_PRIORITIES = ("high", "medium", "low")
MAX_TODOS = 50
MAX_CONTENT_CHARS = 500
TODO_FILE_NAME = "todos.json"


class TodoError(RuntimeError):
    """The checklist payload is invalid."""


def _normalize_entry(raw: object, index: int) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise TodoError(f"第 {index + 1} 项必须是对象")
    content = str(raw.get("content") or "").strip()
    if not content:
        raise TodoError(f"第 {index + 1} 项 content 不能为空")
    if len(content) > MAX_CONTENT_CHARS:
        raise TodoError(f"第 {index + 1} 项 content 超过 {MAX_CONTENT_CHARS} 字符")
    status = str(raw.get("status") or "pending").strip().lower()
    if status not in TODO_STATUSES:
        raise TodoError(
            f"第 {index + 1} 项 status 非法: {status!r} ({'|'.join(TODO_STATUSES)})"
        )
    priority = str(raw.get("priority") or "medium").strip().lower()
    if priority not in TODO_PRIORITIES:
        raise TodoError(
            f"第 {index + 1} 项 priority 非法: {priority!r} ({'|'.join(TODO_PRIORITIES)})"
        )
    return {"content": content, "status": status, "priority": priority}


def normalize_todos(raw_todos: object) -> list[dict[str, str]]:
    """Validate and normalize a full checklist payload (replace semantics)."""
    if not isinstance(raw_todos, list):
        raise TodoError("todos 必须是数组")
    if len(raw_todos) > MAX_TODOS:
        raise TodoError(f"todos 最多 {MAX_TODOS} 项 (收到 {len(raw_todos)})")
    todos = [_normalize_entry(raw, index) for index, raw in enumerate(raw_todos)]
    in_progress = [todo for todo in todos if todo["status"] == "in_progress"]
    if len(in_progress) > 1:
        raise TodoError("同一时间只允许一项 in_progress")
    return todos


class TodoTools:
    """Workspace-scoped checklist storage for the todo_write / todo_read tools."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace)
        self.path = self.workspace / ".minicc" / TODO_FILE_NAME

    def _atomic_write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(f".{os.getpid()}.{time.time_ns()}.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def read(self, _args: dict[str, object]) -> ToolResult:
        todos: list[dict[str, str]] = []
        updated_at = ""
        if self.path.is_file():
            try:
                stored = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                stored = {}
            raw_todos = stored.get("todos")
            todos = raw_todos if isinstance(raw_todos, list) else []
            updated_at = str(stored.get("updated_at") or "")
        summary = _summarize(todos)
        return ToolResult(
            status="ok",
            summary=summary + (f"（更新于 {updated_at}）" if updated_at else "（尚无清单）"),
            output=json.dumps(todos, ensure_ascii=False, indent=2),
            data={"todos": todos, "updated_at": updated_at, "source": "read"},
            security_tags=["untrusted"],
        )

    def write(self, args: dict[str, object]) -> ToolResult:
        todos = normalize_todos(args.get("todos"))
        updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._atomic_write({"todos": todos, "updated_at": updated_at})
        summary = _summarize(todos)
        lines = [
            f"[{index + 1}] ({todo['priority']}) {todo['content']} — {todo['status']}"
            for index, todo in enumerate(todos)
        ]
        return ToolResult(
            status="ok",
            summary=summary,
            output="\n".join(lines) or "(清单已清空)",
            data={"todos": todos, "updated_at": updated_at, "source": "write"},
            security_tags=["untrusted"],
        )


def _summarize(todos: list[dict[str, str]]) -> str:
    counts = {status: 0 for status in TODO_STATUSES}
    for todo in todos:
        counts[todo["status"]] += 1
    return (
        f"任务清单已更新：{counts['completed']} completed / "
        f"{counts['in_progress']} in_progress / {counts['pending']} pending"
    )


__all__ = [
    "MAX_CONTENT_CHARS",
    "MAX_TODOS",
    "TodoError",
    "TodoTools",
    "normalize_todos",
]
