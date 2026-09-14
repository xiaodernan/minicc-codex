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

    def get(self, task_id: str) -> dict[str, Any] | None:
        """Load one snapshot by id (worker-process progress polling)."""
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM tasks WHERE task_id = ?", (str(task_id),)
            ).fetchone()
        if row is None:
            return None
        try:
            value = json.loads(row["payload"])
        except (TypeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def search(
        self,
        query: str,
        *,
        limit: int = 50,
        workspace_path: str | None = None,
    ) -> list[dict[str, Any]]:
        """Full-text-ish history search over stored task snapshots.

        SQLite ``instr(lower(...), lower(...))`` acts as a cheap ASCII
        case-insensitive prefilter; the authoritative match, snippet, and
        match count are computed in Python over the parsed snapshot fields so
        Unicode folding behaves correctly. Snapshots were redacted at upsert
        time; snippets are redacted again for defense in depth.
        """
        needle = str(query or "").strip()
        if not needle:
            return []
        limit = max(1, min(int(limit), 100))
        sql = "SELECT task_id, created_at, workspace_path, payload FROM tasks WHERE instr(lower(payload), lower(?)) > 0"
        params: list[Any] = [needle]
        if workspace_path:
            sql += " AND workspace_path = ?"
            params.append(workspace_path)
        # Keep the SQL prefilter broad (LIMIT 400) so Python-side ranking can
        # fill the user limit even when some rows only match in metadata.
        sql += " ORDER BY created_at DESC LIMIT 400"
        results: list[dict[str, Any]] = []
        with self._lock, self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        for row in rows:
            try:
                value = json.loads(row["payload"])
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(value, dict):
                continue
            if not value.get("task_id") or "[REDACTED:llm_api_key]" in str(value.get("task_id")):
                value["task_id"] = str(row["task_id"])
            match = _search_snapshot(value, needle)
            if match is None:
                continue
            results.append(
                {
                    "task_id": value.get("task_id"),
                    "workspace_path": str(value.get("workspace_path") or row["workspace_path"] or ""),
                    "status": str(value.get("status") or ""),
                    "created_at": value.get("created_at"),
                    "finished_at": value.get("finished_at"),
                    "prompt_preview": str(value.get("preview") or value.get("prompt") or "")[:160],
                    "snippet": match["snippet"],
                    "match_count": match["match_count"],
                }
            )
            if len(results) >= limit:
                break
        return results

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

_SNIPPET_CONTEXT_CHARS = 80
_MAX_MATCH_COUNT = 999


def _searchable_text(snapshot: dict[str, Any]) -> str:
    """Concatenate the user-visible text fields a history search should cover."""
    parts: list[str] = [str(snapshot.get("prompt") or "")]
    result_payload = snapshot.get("result")
    if isinstance(result_payload, dict):
        parts.append(str(result_payload.get("answer") or ""))
    parts.append(str(snapshot.get("stream_text") or ""))
    parts.append(str(snapshot.get("error") or ""))
    return "\n".join(part for part in parts if part)


def _search_snapshot(snapshot: dict[str, Any], needle: str) -> dict[str, Any] | None:
    """Return snippet + match count for ``needle`` inside one snapshot."""
    haystack = _searchable_text(snapshot)
    folded_haystack = haystack.casefold()
    folded_needle = needle.casefold()
    first = folded_haystack.find(folded_needle)
    if first < 0:
        return None
    match_count = min(folded_haystack.count(folded_needle), _MAX_MATCH_COUNT)
    start = max(0, first - _SNIPPET_CONTEXT_CHARS)
    end = min(len(haystack), first + len(needle) + _SNIPPET_CONTEXT_CHARS)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(haystack) else ""
    snippet = f"{prefix}{haystack[start:end]}{suffix}"
    return {"snippet": redact_text(snippet)[0], "match_count": match_count}


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
