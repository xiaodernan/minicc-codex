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
        payload = {
            "version": 1,
            "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "messages": [self._redacted_message(message) for message in messages],
        }
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
