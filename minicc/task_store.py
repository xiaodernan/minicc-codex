"""Small durable task store for the local web agent.

SQLite keeps task history and resumable metadata across browser refreshes and
service restarts without introducing a separate daemon or dependency.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .tools.registry import redact_text


TERMINAL_TASK_STATUSES = frozenset({"completed", "failed", "cancelled", "interrupted"})


class TaskStore:
    """Persist one JSON snapshot per task in a local SQLite database."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    workspace_path TEXT NOT NULL DEFAULT '',
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def upsert(self, snapshot: dict[str, Any]) -> None:
        task_id = str(snapshot.get("task_id") or "")
        if not task_id:
            return
        payload = _redact(snapshot)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks(task_id, created_at, workspace_path, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    created_at=excluded.created_at,
                    workspace_path=excluded.workspace_path,
                    payload=excluded.payload
                """,
                (
                    task_id,
                    float(snapshot.get("created_at_epoch") or 0),
                    str(snapshot.get("workspace_path") or ""),
                    json.dumps(payload, ensure_ascii=False),
                ),
            )

    def load(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT task_id, payload FROM tasks ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 1000)),),
            ).fetchall()
        output: list[dict[str, Any]] = []
        for row in rows:
            try:
                value = json.loads(row["payload"])
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                # Older versions redacted the ``sk-`` substring inside
                # ``task-...``. The relational primary key is authoritative
                # and lets those records recover without data loss.
                if not value.get("task_id") or "[REDACTED:llm_api_key]" in str(value.get("task_id")):
                    value["task_id"] = str(row["task_id"])
                output.append(value)
        return output

    def prune(
        self,
        *,
        keep_terminal: int = 24,
        max_age_days: int | None = 30,
        vacuum: bool = False,
    ) -> list[str]:
        """Remove old terminal snapshots while preserving active work.

        The newest ``keep_terminal`` terminal records are retained, subject to
        the age limit. Queued/running records are always retained, and child
        records referenced by a retained batch are kept for inspectability.
        Malformed records are left untouched so maintenance cannot destroy
        data it cannot understand.
        """
        keep_terminal = max(0, min(int(keep_terminal), 1000))
        cutoff = None if max_age_days is None else time.time() - max(1, int(max_age_days)) * 86400
        deleted: list[str] = []
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT task_id, created_at, payload FROM tasks ORDER BY created_at DESC"
            ).fetchall()
            terminal: list[sqlite3.Row] = []
            parsed: dict[str, dict[str, Any]] = {}
            for row in rows:
                try:
                    value = json.loads(row["payload"])
                except (TypeError, json.JSONDecodeError):
                    continue
                if not isinstance(value, dict):
                    continue
                parsed[str(row["task_id"])] = value
                if str(value.get("status") or "") in TERMINAL_TASK_STATUSES:
                    terminal.append(row)

            retained = {
                str(row["task_id"])
                for index, row in enumerate(terminal)
                if index < keep_terminal and (cutoff is None or float(row["created_at"] or 0) >= cutoff)
            }
            # Keep the history needed to explain a retained batch task.
            pending = list(retained)
            while pending:
                parent_id = pending.pop()
                for child_id in parsed.get(parent_id, {}).get("child_task_ids") or []:
                    child_key = str(child_id)
                    if child_key in parsed and child_key not in retained:
                        retained.add(child_key)
                        pending.append(child_key)

            for row in terminal:
                task_id = str(row["task_id"])
                if task_id not in retained:
                    deleted.append(task_id)
            if deleted:
                connection.executemany("DELETE FROM tasks WHERE task_id = ?", [(task_id,) for task_id in deleted])

        if deleted and vacuum:
            with self._lock, self._connect() as connection:
                connection.execute("VACUUM")
        return deleted


_IDENTITY_KEYS = frozenset({"task_id", "session_id", "workspace_path", "parent_id", "child_task_ids"})


def _redact(value: Any, key: str | None = None) -> Any:
    if key in _IDENTITY_KEYS:
        return value
    if isinstance(value, str):
        return redact_text(value)[0]
    if isinstance(value, list):
        return [_redact(item, key) for item in value]
    if isinstance(value, dict):
        return {str(item_key): _redact(item, str(item_key)) for item_key, item in value.items()}
    return value


__all__ = ["TaskStore"]
