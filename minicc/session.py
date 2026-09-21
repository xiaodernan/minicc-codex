"""Small, local, redacted session checkpoints for reconnectable work."""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
import time
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

class SessionStore:
    """Persist one conversation under workspace/.minicc/sessions."""

    def __init__(self, workspace: Path, session_id: str = "latest") -> None:
        if not _SESSION_ID.fullmatch(session_id):
            raise SessionError(f"非法 session id: {session_id!r}")
        self.path = workspace / ".minicc" / "sessions" / f"{session_id}.json"

    @property
    def exists(self) -> bool:
        return self.path.is_file()

    def load(self, system_prompt: str) -> list[dict[str, Any]]:
        if not self.exists:
            return [{"role": "system", "content": system_prompt}]
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SessionError(f"无法读取 session {self.path}: {exc}") from exc
        raw_messages = payload.get("messages") if isinstance(payload, dict) else None
        if not isinstance(raw_messages, list):
            raise SessionError(f"session 格式错误: {self.path}")
        messages = [self._validate_message(item) for item in raw_messages]
        if not messages or messages[0].get("role") != "system":
            messages.insert(0, {"role": "system", "content": system_prompt})
        else:
            messages[0] = {"role": "system", "content": system_prompt}
        return messages

    def save(self, messages: list[dict[str, Any]]) -> None:
        view = self.load_view() if self.exists else dict(_DEFAULT_VIEW)
        payload = {
            "version": 1,
            "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "messages": [self._redacted_message(message) for message in messages],
            "view": view,
        }
        self._write_payload(payload)

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
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SessionError(f"无法读取 session {self.path}: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
            raise SessionError(f"session 格式错误: {self.path}")
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
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SessionError(f"无法读取 session {self.path}: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
            raise SessionError(f"session 格式错误: {self.path}")
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
                os.replace(temp_path, target)
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
