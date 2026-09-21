"""Small, local, redacted session checkpoints for reconnectable work.

M8-T2 adds the message-level event tree on top of the checkpoint store: every
persisted message carries a stable ``id`` (``m-<hex>``) that is re-derived by
content matching on each save, and ``fork()`` branches a conversation at any
message into a *new, independent* session file recording its
``forked_from`` lineage. The collection of session files under
``.minicc/sessions`` plus those lineage links is the tree; loading still hands
the agent loop the plain linear message list it expects (ids stripped).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import secrets
import tempfile
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .tools.registry import redact_text

try:  # Windows
    import msvcrt
except ImportError:  # pragma: no cover - non-Windows
    msvcrt = None  # type: ignore[assignment]

try:  # POSIX
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

_SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_ALLOWED_ROLES = {"system", "user", "assistant", "tool"}
_DEFAULT_VIEW = {
    "version": 1,
    "last_item": 0,
    "last_tool": 0,
    "compact_tools": True,
    "tool_history": [],
}

# M3-T7: serialise the atomic replace across processes (and threads). The web
# process and detached worker subprocesses each have their own in-process locks,
# so only an OS-level lock on a sidecar file prevents two writers from racing
# on os.replace and tearing the session JSON.
_LOCK_ATTEMPTS = 400
_LOCK_RETRY_DELAY = 0.05

# Windows sharing violation: a reader that holds the target open without the
# sidecar lock (load/list/_stored_payload_or_none) makes os.replace fail with
# WinError 5 exactly while the replace is attempted. The retry is safe: the
# temp file survives until a replace succeeds, so retrying is idempotent.
_REPLACE_ATTEMPTS = 24
_REPLACE_RETRY_DELAY = 0.05


@contextlib.contextmanager
def _cross_process_lock(lock_path: Path):
    """Best-effort exclusive lock on ``lock_path``; degrades to no-op if unsupported."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+")
    locked = False
    try:
        if msvcrt is not None:
            handle.seek(0)
            for _ in range(_LOCK_ATTEMPTS):
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                    locked = True
                    break
                except OSError:
                    time.sleep(_LOCK_RETRY_DELAY)
            if not locked:
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                locked = True
        elif fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            locked = True
        yield
    finally:
        try:
            if locked and msvcrt is not None:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            elif locked and fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


class SessionError(RuntimeError):
    """A session checkpoint is invalid or cannot be read/written."""


def _replace_with_retry(source: Path, target: Path) -> None:
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == _REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(_REPLACE_RETRY_DELAY)

class SessionStore:
    """Persist one conversation under workspace/.minicc/sessions."""

    def __init__(self, workspace: Path, session_id: str = "latest") -> None:
        if not _SESSION_ID.fullmatch(session_id):
            raise SessionError(f"非法 session id: {session_id!r}")
        self.workspace = Path(workspace)
        self.session_id = session_id
        self.path = workspace / ".minicc" / "sessions" / f"{session_id}.json"

    @property
    def exists(self) -> bool:
        return self.path.is_file()

    def load(self, system_prompt: str) -> list[dict[str, Any]]:
        if not self.exists:
            return [{"role": "system", "content": system_prompt}]
        payload = self._read_payload()
        messages = [self._strip_message_id(self._validate_message(item)) for item in payload["messages"]]
        if not messages or messages[0].get("role") != "system":
            messages.insert(0, {"role": "system", "content": system_prompt})
        else:
            messages[0] = {"role": "system", "content": system_prompt}
        return messages

    def save(self, messages: list[dict[str, Any]]) -> None:
        stored = self._stored_payload_or_none()
        payload = {
            "version": 1,
            "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "messages": self._with_message_ids(messages, stored),
            "view": self.load_view() if self.exists else dict(_DEFAULT_VIEW),
        }
        if isinstance(stored, dict):
            # Fork lineage and the original creation time survive every save.
            for key in ("forked_from", "created_at"):
                if stored.get(key) is not None:
                    payload[key] = stored[key]
        self._write_payload(payload)

    # -- message-level event tree (M8-T2) ------------------------------------

    def _read_payload(self) -> dict[str, Any]:
        if not self.exists:
            raise SessionError(f"会话不存在: {self.path.name}")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SessionError(f"无法读取 session {self.path}: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
            raise SessionError(f"session 格式错误: {self.path}")
        return payload

    def _stored_payload_or_none(self) -> dict[str, Any] | None:
        """Best-effort read of the current checkpoint file (never raises)."""
        if not self.exists:
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _message_key(message: dict[str, Any]) -> str:
        """Content fingerprint of a stored message, ignoring its id field."""
        identity = {key: message.get(key) for key in ("role", "content", "tool_calls", "tool_call_id")}
        digest = hashlib.sha256(
            json.dumps(identity, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        ).hexdigest()
        return digest[:20]

    @staticmethod
    def _strip_message_id(message: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in message.items() if key != "id"}

    def _with_message_ids(
        self,
        messages: list[dict[str, Any]],
        stored: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Assign stable ids to the sanitized payload.

        Ids are matched to the previous on-disk list by content fingerprint
        (FIFO per fingerprint), so appends keep existing ids and compacted or
        rewritten messages simply receive fresh ones. The live message list
        passed by the agent loop is never mutated.
        """
        if stored is None:
            stored = self._stored_payload_or_none()
        previous: dict[str, deque[str]] = {}
        stored_messages = stored.get("messages") if isinstance(stored, dict) else None
        if isinstance(stored_messages, list):
            for item in stored_messages:
                if isinstance(item, dict) and isinstance(item.get("id"), str):
                    previous.setdefault(self._message_key(item), deque()).append(item["id"])
        stamped: list[dict[str, Any]] = []
        for message in messages:
            cleaned = self._redacted_message(message)
            stamped_message = dict(cleaned)
            queue = previous.get(self._message_key(cleaned))
            if queue:
                stamped_message["id"] = queue.popleft()
            else:
                stamped_message["id"] = f"m-{secrets.token_hex(4)}"
            stamped.append(stamped_message)
        return stamped

    def fork(
        self,
        from_message_id: int | str,
        *,
        new_session_id: str | None = None,
    ) -> "SessionStore":
        """Branch this conversation at one message into a new session file.

        ``from_message_id`` is either a stored message id (``m-…``, keep
        through that message) or a 1-based message count including the system
        turn (same semantics as ``rewind``). The fork inherits the history
        prefix but lives in its own file with ``forked_from`` lineage, so
        later writes never touch the source session.
        """
        payload = self._read_payload()
        messages = [item for item in payload["messages"] if isinstance(item, dict)]
        resolved_id: str | None = None
        if isinstance(from_message_id, str) and from_message_id.strip():
            wanted = from_message_id.strip()
            positions = [index for index, item in enumerate(messages) if item.get("id") == wanted]
            if not positions:
                raise SessionError(f"会话 {self.session_id} 中没有消息 id {wanted!r}（fork 点无效）")
            keep = positions[-1] + 1
            resolved_id = wanted
        else:
            keep = _non_negative_int(from_message_id)
        if keep < 1:
            raise SessionError("fork 点至少为 1（保留 system 消息）")
        if keep > len(messages):
            raise SessionError(f"fork 点 {keep} 超出会话消息数 {len(messages)}")
        if resolved_id is None:
            tail = messages[keep - 1]
            if isinstance(tail.get("id"), str):
                resolved_id = str(tail["id"])
        target_id = str(new_session_id or f"{self.session_id[:48]}-fork-{secrets.token_hex(2)}")
        store = SessionStore(self.workspace, target_id)
        if store.exists:
            raise SessionError(f"目标会话已存在: {target_id}")
        now = datetime.now(UTC).isoformat(timespec="seconds")
        fork_payload = {
            "version": 1,
            "created_at": now,
            "updated_at": now,
            "messages": json.loads(json.dumps(messages[:keep], ensure_ascii=False)),
            "forked_from": {
                "session": self.session_id,
                "from_message_id": resolved_id or "",
                "keep_messages": keep,
                "at": now,
            },
            "view": dict(_DEFAULT_VIEW),
        }
        store._write_payload(fork_payload)
        return store

    def rewind(self, keep_messages: int) -> dict[str, Any]:
        """Truncate the conversation to ``keep_messages`` entries.

        Message-level rewind: the full current payload is backed up to
        ``<session>.pre-rewind.json`` (rotating single backup) before the
        truncation is written, so a mistaken rewind can be recovered manually.
        The system message at index 0 always survives; ``keep_messages`` counts
        from the full list including system. Rewinding past the end is a no-op
        returning ``removed: 0``.
        """
        keep = _non_negative_int(keep_messages)
        if not self.exists:
            raise SessionError(f"会话不存在: {self.path.name}")
        payload = self._read_payload()
        messages = payload["messages"]
        total = len(messages)
        if total == 0 or keep < 1:
            raise SessionError("keep_messages 至少为 1（保留 system 消息）")
        if keep >= total:
            return {"kept": total, "removed": 0, "backup": ""}
        backup_path = self.path.with_name(f"{self.path.stem}.pre-rewind.json")
        self._write_payload_at(backup_path, payload)
        payload["messages"] = messages[:keep]
        payload["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        payload["rewound_at"] = payload["updated_at"]
        payload["rewound_removed"] = total - keep
        self._write_payload(payload)
        return {"kept": keep, "removed": total - keep, "backup": backup_path.name}

    def rewind_to_user_index(self, user_index: int) -> dict[str, Any]:
        """Keep through the Nth user message (1-based), including system.

        Intervening assistant/tool messages before that user turn are kept;
        everything after it is dropped. ``user_index`` counts only ``role=user``.
        """
        n = _non_negative_int(user_index)
        if n < 1:
            raise SessionError("user_index 至少为 1")
        if not self.exists:
            raise SessionError(f"会话不存在: {self.path.name}")
        payload = self._read_payload()
        messages = payload["messages"]
        seen = 0
        keep: int | None = None
        for index, message in enumerate(messages):
            if isinstance(message, dict) and message.get("role") == "user":
                seen += 1
                if seen == n:
                    keep = index + 1
                    break
        if keep is None:
            raise SessionError(f"会话中没有第 {n} 条 user 消息")
        result = self.rewind(keep)
        result["user_index"] = n
        return result

    def _write_payload_at(self, target: Path, payload: dict[str, Any]) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        # Per-call unique temp name (mkstemp) so concurrent writers in different
        # processes never share a ".tmp" path; the replace is serialised by the
        # cross-process lock and is atomic on the same filesystem.
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
        )
        temp_path = Path(temp_name)
        consumed = False
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            with _cross_process_lock(target.with_name(target.name + ".lock")):
                _replace_with_retry(temp_path, target)
            consumed = True
        except OSError as exc:
            raise SessionError(f"无法写入 {target}: {exc}") from exc
        finally:
            if not consumed:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def load_view(self) -> dict[str, Any]:
        """Load the CLI's small semantic reading anchor, never raw terminal state."""
        if not self.exists:
            return dict(_DEFAULT_VIEW)
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SessionError(f"无法读取 session 视图 {self.path}: {exc}") from exc
        raw = payload.get("view") if isinstance(payload, dict) else None
        if not isinstance(raw, dict):
            return dict(_DEFAULT_VIEW)
        view = dict(_DEFAULT_VIEW)
        view["last_item"] = _non_negative_int(raw.get("last_item"))
        view["last_tool"] = _non_negative_int(raw.get("last_tool"))
        view["compact_tools"] = bool(raw.get("compact_tools", True))
        history = raw.get("tool_history")
        if isinstance(history, list):
            view["tool_history"] = [
                self._redacted_view_item(item)
                for item in history[-24:]
                if isinstance(item, dict)
            ]
        return view

    def save_view(self, view: dict[str, Any]) -> None:
        """Persist view preferences and the bounded expandable tool index."""
        if not self.exists:
            payload: dict[str, Any] = {"version": 1, "messages": []}
        else:
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise SessionError(f"无法读取 session {self.path}: {exc}") from exc
            payload = raw if isinstance(raw, dict) else {"version": 1, "messages": []}
        payload["version"] = 1
        payload["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        payload["view"] = self.load_view_payload(view)
        self._write_payload(payload)

    def load_view_payload(self, view: dict[str, Any] | None) -> dict[str, Any]:
        """Normalize a view payload before it is written to disk."""
        raw = view if isinstance(view, dict) else {}
        history = raw.get("tool_history")
        return {
            "version": 1,
            "last_item": _non_negative_int(raw.get("last_item")),
            "last_tool": _non_negative_int(raw.get("last_tool")),
            "compact_tools": bool(raw.get("compact_tools", True)),
            "tool_history": [
                self._redacted_view_item(item)
                for item in history[-24:]
                if isinstance(item, dict)
            ] if isinstance(history, list) else [],
        }

    @staticmethod
    def _redacted_view_item(item: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "index": item.get("index"),
            "tool": item.get("tool"),
            "summary": item.get("summary"),
            "command": item.get("command"),
            "output": item.get("output"),
        }
        return {
            str(key): redact_text(str(value))[0]
            for key, value in allowed.items()
            if value not in (None, "")
        }

    def _write_payload(self, payload: dict[str, Any]) -> None:
        self._write_payload_at(self.path, payload)

    @staticmethod
    def _validate_message(message: Any) -> dict[str, Any]:
        if not isinstance(message, dict) or message.get("role") not in _ALLOWED_ROLES:
            raise SessionError("session 包含非法消息")
        return dict(message)

    @staticmethod
    def _redacted_message(message: dict[str, Any]) -> dict[str, Any]:
        def clean(value: Any) -> Any:
            if isinstance(value, str):
                return redact_text(value)[0]
            if isinstance(value, list):
                return [clean(item) for item in value]
            if isinstance(value, dict):
                return {str(key): clean(item) for key, item in value.items()}
            return value

        return clean(message)


def _non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def _first_user_title(messages: list[Any]) -> str:
    for item in messages:
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        content = item.get("content")
        if isinstance(content, list):
            content = " ".join(
                str(part.get("text"))
                for part in content
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            )
        text = " ".join(str(content or "").split())
        if text:
            return redact_text(text[:80])[0]
    return ""


def list_sessions(workspace: Path) -> list[dict[str, Any]]:
    """Describe every stored session (a fork is just another session file).

    The message-level event tree spans files: each entry carries
    ``forked_from`` lineage so callers can render the forest; unreadable or
    malformed checkpoints are reported with an ``error`` field instead of
    raising, so listing never breaks on one bad file. Backup sidecars
    (``*.pre-rewind.json``) are not sessions and are skipped.
    """
    root = Path(workspace) / ".minicc" / "sessions"
    sessions: list[dict[str, Any]] = []
    if not root.is_dir():
        return sessions
    for path in sorted(root.glob("*.json")):
        if path.name.endswith(".pre-rewind.json") or path.name.startswith("."):
            continue
        entry: dict[str, Any] = {"session_id": path.stem, "messages": 0}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            entry["error"] = "无法读取"
            sessions.append(entry)
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
            entry["error"] = "格式错误"
            sessions.append(entry)
            continue
        messages = payload["messages"]
        entry["messages"] = len(messages)
        entry["updated_at"] = str(payload.get("updated_at") or "")
        lineage = payload.get("forked_from")
        entry["forked_from"] = lineage if isinstance(lineage, dict) else None
        entry["title"] = _first_user_title(messages)
        sessions.append(entry)
    return sessions
