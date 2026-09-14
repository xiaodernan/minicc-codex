"""Small, local, redacted session checkpoints for reconnectable work."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .tools.registry import redact_text

_SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_ALLOWED_ROLES = {"system", "user", "assistant", "tool"}
_DEFAULT_VIEW = {
    "version": 1,
    "last_item": 0,
    "last_tool": 0,
    "compact_tools": True,
    "tool_history": [],
}


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

    def _write_payload_at(self, target: Path, payload: dict[str, Any]) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, target)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise SessionError(f"无法写入 {target}: {exc}") from exc

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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise SessionError(f"无法保存 session {self.path}: {exc}") from exc

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
