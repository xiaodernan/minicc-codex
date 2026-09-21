"""Per-session tool/path/command allowlist stored under workspace/.minicc."""

from __future__ import annotations

import fnmatch
import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any

from .tools.registry import redact_text

ALLOWLIST_NAME = "allowlist.json"

_lock = threading.RLock()


class AllowlistError(RuntimeError):
    """Allowlist file is missing, malformed, or cannot be written."""


def _path(workspace: Path) -> Path:
    return Path(workspace) / ".minicc" / ALLOWLIST_NAME


def _empty_session() -> dict[str, list[str]]:
    return {"commands": [], "paths": [], "tools": []}


def load_allowlist(workspace: Path) -> dict[str, Any]:
    path = _path(workspace)
    if not path.is_file():
        return {"sessions": {}}
    with _lock:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AllowlistError(f"无法读取 allowlist: {exc}") from exc
    if not isinstance(payload, dict):
        raise AllowlistError("allowlist 必须是对象")
    sessions = payload.get("sessions")
    if sessions is None:
        sessions = {}
    if not isinstance(sessions, dict):
        raise AllowlistError("allowlist.sessions 必须是对象")
    cleaned: dict[str, Any] = {"sessions": {}}
    for session_id, rules in sessions.items():
        if not isinstance(session_id, str) or not session_id.strip():
            continue
        cleaned["sessions"][session_id] = _normalize_rules(rules)
    return cleaned


def _normalize_rules(raw: object) -> dict[str, list[str]]:
    rules = _empty_session()
    if not isinstance(raw, dict):
        return rules
    for key in ("commands", "paths", "tools"):
        value = raw.get(key)
        if not isinstance(value, list):
            continue
        items: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text and text not in items:
                items.append(text[:512])
        rules[key] = items[:128]
    return rules


def save_allowlist(workspace: Path, payload: dict[str, Any]) -> None:
    path = _path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    # M2-T4: unique temp name per write (no fixed .tmp race) + RLock.
    temporary = path.with_name(f"{ALLOWLIST_NAME}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    with _lock:
        try:
            temporary.write_text(body, encoding="utf-8")
            os.replace(temporary, path)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise AllowlistError(f"无法写入 allowlist: {exc}") from exc


def session_rules(workspace: Path, session_id: str) -> dict[str, list[str]]:
    payload = load_allowlist(workspace)
    return _normalize_rules((payload.get("sessions") or {}).get(str(session_id or "").strip()))


def replace_session_rules(
    workspace: Path,
    session_id: str,
    *,
    commands: list[str] | None = None,
    paths: list[str] | None = None,
    tools: list[str] | None = None,
) -> dict[str, list[str]]:
    sid = str(session_id or "").strip()
    if not sid:
        raise AllowlistError("session_id 不能为空")
    # M2-T4: read-modify-write under one lock so concurrent sessions
    # cannot lose each other's rules.
    with _lock:
        payload = load_allowlist(workspace)
        current = _normalize_rules((payload.get("sessions") or {}).get(sid))
        if commands is not None:
            current["commands"] = _normalize_rules({"commands": commands})["commands"]
        if paths is not None:
            current["paths"] = _normalize_rules({"paths": paths})["paths"]
        if tools is not None:
            current["tools"] = _normalize_rules({"tools": tools})["tools"]
        payload.setdefault("sessions", {})[sid] = current
        save_allowlist(workspace, payload)
        return current


def add_session_rule(
    workspace: Path,
    session_id: str,
    *,
    command: str | None = None,
    path: str | None = None,
    tool: str | None = None,
) -> dict[str, list[str]]:
    # M2-T4: persist the redacted command form so (a) the file never holds
    # plaintext secrets and (b) match_session_allowlist (which compares the
    # redacted runtime command) can actually hit on the second call.
    with _lock:
        rules = session_rules(workspace, session_id)
        if command:
            pattern = redact_text(command.strip())[0].strip()
            if pattern and pattern not in rules["commands"]:
                rules["commands"].append(pattern)
        if path:
            pattern = path.strip()
            if pattern and pattern not in rules["paths"]:
                rules["paths"].append(pattern)
        if tool:
            name = tool.strip()
            if name and name not in rules["tools"]:
                rules["tools"].append(name)
        return replace_session_rules(
            workspace,
            session_id,
            commands=rules["commands"],
            paths=rules["paths"],
            tools=rules["tools"],
        )


def _escape_brackets(pattern: str) -> str:
    """Make a stored allowlist pattern match brackets literally.

    ``redact_text`` writes ``[REDACTED:llm_api_key]``; ``fnmatch`` reads that
    as a character class, so the rule could never match the redacted runtime
    command (caught by test_m2t4). ``*``/``?`` keep their wildcard meaning.

    Single pass: chained ``str.replace`` would re-escape the ``[`` inside its
    own ``[[]`` output (``[[[]]``), which matches nothing.
    """
    parts: list[str] = []
    for char in pattern:
        if char == "[":
            parts.append("[[]")
        elif char == "]":
            parts.append("[]]")
        else:
            parts.append(char)
    return "".join(parts)


def _path_from_arguments(arguments: dict[str, Any] | None) -> str:
    if not isinstance(arguments, dict):
        return ""
    for key in ("path", "file", "target"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().replace("\\", "/")
    return ""


def match_session_allowlist(
    workspace: Path,
    session_id: str,
    tool: str,
    arguments: dict[str, Any] | None = None,
) -> bool:
    """True when this tool call is covered by the session allowlist."""
    try:
        rules = session_rules(workspace, session_id)
    except AllowlistError:
        return False
    name = str(tool or "").strip()
    if name and any(fnmatch.fnmatch(name, pattern) for pattern in rules["tools"]):
        return True
    if name == "bash":
        command, _ = redact_text(str((arguments or {}).get("command") or ""))
        command = command.strip()
        if command and any(
            fnmatch.fnmatch(command, _escape_brackets(pattern)) for pattern in rules["commands"]
        ):
            return True
    rel = _path_from_arguments(arguments)
    if rel and any(fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(rel.lstrip("./"), pattern) for pattern in rules["paths"]):
        return True
    return False


__all__ = [
    "AllowlistError",
    "add_session_rule",
    "load_allowlist",
    "match_session_allowlist",
    "replace_session_rules",
    "session_rules",
]
