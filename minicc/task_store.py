"""Small durable task store for the local web agent.

SQLite keeps task history and resumable metadata across browser refreshes and
service restarts without introducing a separate daemon or dependency.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
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
            connection.execute("PRAGMA journal_mode=WAL")
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
            connection.execute("CREATE INDEX IF NOT EXISTS idx_tasks_workspace_created ON tasks(workspace_path, created_at DESC)")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS task_leases (task_id TEXT PRIMARY KEY, owner TEXT NOT NULL, "
                "pid INTEGER NOT NULL, heartbeat REAL NOT NULL, expires REAL NOT NULL)"
            )
            self._initialize_search(connection)

    def _initialize_search(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS task_search (task_id TEXT PRIMARY KEY, created_at REAL NOT NULL, "
            "workspace_path TEXT NOT NULL, search_text TEXT NOT NULL, folded_text TEXT NOT NULL, summary TEXT NOT NULL)"
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_task_search_workspace ON task_search(workspace_path, created_at DESC)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_task_search_created ON task_search(created_at DESC)")
        self._search_fts = False
        try:
            existing_fts = connection.execute("SELECT 1 FROM sqlite_master WHERE name='task_search_fts'").fetchone()
            connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS task_search_fts USING fts5(folded_text, content='task_search', content_rowid='rowid', tokenize='trigram')")
            connection.execute("CREATE TRIGGER IF NOT EXISTS task_search_ai AFTER INSERT ON task_search BEGIN INSERT INTO task_search_fts(rowid, folded_text) VALUES (new.rowid, new.folded_text); END")
            connection.execute("CREATE TRIGGER IF NOT EXISTS task_search_ad AFTER DELETE ON task_search BEGIN INSERT INTO task_search_fts(task_search_fts, rowid, folded_text) VALUES ('delete', old.rowid, old.folded_text); END")
            connection.execute("CREATE TRIGGER IF NOT EXISTS task_search_au AFTER UPDATE ON task_search BEGIN INSERT INTO task_search_fts(task_search_fts, rowid, folded_text) VALUES ('delete', old.rowid, old.folded_text); INSERT INTO task_search_fts(rowid, folded_text) VALUES (new.rowid, new.folded_text); END")
            if not existing_fts:
                connection.execute("INSERT INTO task_search_fts(task_search_fts) VALUES ('rebuild')")
            self._search_fts = True
        except sqlite3.OperationalError:
            # Some bundled SQLite builds omit FTS5/trigram. The projection
            # still avoids searching or decoding large event JSON payloads.
            pass
        # Existing databases are migrated once. Corrupt snapshots remain
        # inspectable but do not enter the user-visible search projection.
        rows = connection.execute("SELECT task_id, payload FROM tasks WHERE task_id NOT IN (SELECT task_id FROM task_search)").fetchall()
        for row in rows:
            try:
                snapshot = json.loads(row["payload"])
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(snapshot, dict):
                snapshot["task_id"] = str(row["task_id"])
                self._write_search(connection, _redact(snapshot))

    @staticmethod
    def _write_search(connection: sqlite3.Connection, snapshot: dict[str, Any]) -> None:
        visible_text = _searchable_text(snapshot)
        summary = {key: snapshot.get(key) for key in ("task_id", "workspace_path", "status", "created_at", "finished_at")}
        summary["prompt_preview"] = str(snapshot.get("preview") or snapshot.get("prompt") or "")[:160]
        connection.execute(
            "INSERT INTO task_search(task_id, created_at, workspace_path, search_text, folded_text, summary) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(task_id) DO UPDATE SET created_at=excluded.created_at, workspace_path=excluded.workspace_path, "
            "search_text=excluded.search_text, folded_text=excluded.folded_text, summary=excluded.summary "
            "WHERE task_search.created_at != excluded.created_at OR task_search.workspace_path != excluded.workspace_path "
            "OR task_search.search_text != excluded.search_text OR task_search.summary != excluded.summary",
            (str(snapshot["task_id"]), float(snapshot.get("created_at_epoch") or 0), str(snapshot.get("workspace_path") or ""),
             visible_text, visible_text.casefold(), json.dumps(summary, ensure_ascii=False)),
        )

    @contextmanager
    def _connect(self):
        """Commit/rollback and close every connection; sqlite's context alone leaks it."""
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def claim_lease(self, task_id: str, owner: str, *, pid: int = 0, ttl: float = 45.0) -> bool:
        """Atomically reserve execution; a different live owner cannot be replaced."""
        now = time.time()
        with self._lock, self._connect() as connection:
            changed = connection.execute(
                "INSERT INTO task_leases(task_id, owner, pid, heartbeat, expires) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(task_id) DO UPDATE SET owner=excluded.owner, pid=excluded.pid, "
                "heartbeat=excluded.heartbeat, expires=excluded.expires "
                "WHERE task_leases.expires <= ? OR task_leases.owner = excluded.owner",
                (task_id, owner, pid, now, now + ttl, now),
            ).rowcount
        return changed == 1

    def heartbeat_lease(self, task_id: str, owner: str, *, pid: int, ttl: float = 45.0) -> bool:
        now = time.time()
        with self._lock, self._connect() as connection:
            # M3-T5: `expires > now` fence — an already-expired lease must NOT
            # be revivable by a late heartbeat, otherwise has_live_worker keeps
            # reporting a dead worker as alive and auto-resume refuses to
            # re-queue the task forever. claim_lease has the same fence.
            changed = connection.execute(
                "UPDATE task_leases SET heartbeat=?, expires=?, pid=? "
                "WHERE task_id=? AND owner=? AND expires > ?",
                (now, now + ttl, pid, task_id, owner, now),
            ).rowcount
        return changed == 1

    def get_lease(self, task_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT * FROM task_leases WHERE task_id=?", (task_id,)).fetchone()
        return dict(row) if row is not None else None

    def release_lease(self, task_id: str, owner: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM task_leases WHERE task_id=? AND owner=?", (task_id, owner))

    def upsert(self, snapshot: dict[str, Any], *, lease_owner: str | None = None) -> bool:
        task_id = str(snapshot.get("task_id") or "")
        if not task_id:
            return False
        payload = _redact(snapshot)
        with self._lock, self._connect() as connection:
            if lease_owner is not None:
                # Fence expired/replaced workers in the same transaction as
                # the write. An old process must never overwrite its successor.
                connection.execute("BEGIN IMMEDIATE")
                lease = connection.execute("SELECT owner, expires FROM task_leases WHERE task_id=?", (task_id,)).fetchone()
                if lease is None or lease["owner"] != lease_owner or float(lease["expires"]) <= time.time():
                    return False
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
            self._write_search(connection, payload)
        return True

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
        """Search redacted visible text without scanning serialized events.

        Trigram FTS narrows substring queries when available; short queries
        use the compact projection. Casefolding is identical in both paths.
        """
        needle = str(query or "").strip()
        if not needle:
            return []
        limit = max(1, min(int(limit), 100))
        folded = needle.casefold()
        sql = "SELECT search_text, summary FROM task_search WHERE instr(folded_text, ?) > 0"
        params: list[Any] = [folded]
        if self._search_fts and len(folded) >= 3 and "\x00" not in folded:
            sql += " AND rowid IN (SELECT rowid FROM task_search_fts WHERE task_search_fts MATCH ?)"
            params.append('"' + folded.replace('"', '""') + '"')
        if workspace_path:
            sql += " AND workspace_path = ?"
            params.append(workspace_path)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        results: list[dict[str, Any]] = []
        with self._lock, self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        for row in rows:
            try:
                value = json.loads(row["summary"])
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(value, dict):
                continue
            match = _search_text(str(row["search_text"]), needle)
            if match is None:
                continue
            results.append(
                {
                    "task_id": value.get("task_id"),
                    "workspace_path": str(value.get("workspace_path") or ""),
                    "status": str(value.get("status") or ""),
                    "created_at": value.get("created_at"),
                    "finished_at": value.get("finished_at"),
                    "prompt_preview": str(value.get("prompt_preview") or ""),
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
                connection.executemany("DELETE FROM task_search WHERE task_id = ?", [(task_id,) for task_id in deleted])
                connection.executemany("DELETE FROM task_leases WHERE task_id = ?", [(task_id,) for task_id in deleted])

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
    return _search_text(_searchable_text(snapshot), needle)


def _search_text(haystack: str, needle: str) -> dict[str, Any] | None:
    folded_haystack = haystack.casefold()
    folded_needle = needle.casefold()
    first = folded_haystack.find(folded_needle)
    if first < 0:
        return None
    match_count = min(folded_haystack.count(folded_needle), _MAX_MATCH_COUNT)
    # Casefold can expand one character (Straße -> strasse). Convert offsets
    # back to original text so a long prefix never pushes the match out.
    folded_offset = 0
    original_start, original_end = 0, len(haystack)
    for index, character in enumerate(haystack):
        next_offset = folded_offset + len(character.casefold())
        if folded_offset <= first < next_offset:
            original_start = index
        if next_offset >= first + len(folded_needle):
            original_end = index + 1
            break
        folded_offset = next_offset
    start = max(0, original_start - _SNIPPET_CONTEXT_CHARS)
    end = min(len(haystack), original_end + _SNIPPET_CONTEXT_CHARS)
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
