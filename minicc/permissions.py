"""M7-T3 declarative workspace permission rules (`.minicc/permissions.json`).

Same rule shape as the session allowlist (tool names, redacted bash command
patterns, path patterns) so one mental model covers allowlist / hooks /
permissions. Unlike the per-session allowlist this file is user-authored,
project-scoped and checked into the workspace:

* ``deny`` rules are absolute — they short-circuit *before* the interactive
  approval prompt and cannot be overridden by task flags or allow rules.
* ``allow`` rules only skip the interactive prompt for decisions the mode
  would otherwise ask about (missing_task_write / missing_task_exec). They
  never escalate: plan mode stays read-only and network exec still needs
  the network grant.

A malformed file is non-fatal (mirrors hooks.json): the rules are ignored
and the parse error surfaces in the returned ``error`` for audit events.
"""

from __future__ import annotations

import fnmatch
import json
import threading
from pathlib import Path
from typing import Any

from .allowlist import _escape_brackets, _path_from_arguments
from .tools.registry import redact_text

PERMISSIONS_NAME = "permissions.json"

_lock = threading.RLock()
# (path, mtime_ns, size) -> (rules, error); file reads stay off the hot path.
_cache: dict[str, tuple[tuple[int, int], tuple[dict[str, list[str]], str]]] = {}


class PermissionConfigError(ValueError):
    """permissions.json is malformed at the schema level (non-fatal)."""


def _empty_rules() -> dict[str, list[str]]:
    return {"allow": {"tools": [], "commands": [], "paths": []},
            "deny": {"tools": [], "commands": [], "paths": []}}


def _normalize_side(raw: object) -> dict[str, list[str]]:
    side = {"tools": [], "commands": [], "paths": []}
    if not isinstance(raw, dict):
        return side
    for key in ("tools", "commands", "paths"):
        value = raw.get(key)
        if not isinstance(value, list):
            continue
        items: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text and text not in items:
                items.append(text[:512])
        side[key] = items[:256]
    return side


def _validate(payload: object) -> tuple[dict[str, list[str]], str]:
    rules = _empty_rules()
    if not isinstance(payload, dict):
        raise PermissionConfigError("permissions.json 顶层必须是 JSON 对象")
    unknown = set(payload) - {"allow", "deny", "permissions"}
    if unknown:
        raise PermissionConfigError(f"未知字段: {', '.join(sorted(unknown))}")
    body = payload.get("permissions") if isinstance(payload.get("permissions"), dict) else payload
    if not isinstance(body, dict):
        raise PermissionConfigError("permissions 必须是 JSON 对象")
    rules["allow"] = _normalize_side(body.get("allow"))
    rules["deny"] = _normalize_side(body.get("deny"))
    return rules, ""


def _match_patterns(tool: str, arguments: dict[str, Any] | None, side: dict[str, list[str]]) -> bool:
    name = str(tool or "").strip()
    if name and any(fnmatch.fnmatch(name, pattern) for pattern in side["tools"]):
        return True
    if name == "bash":
        command, _ = redact_text(str((arguments or {}).get("command") or ""))
        command = command.strip()
        if command and any(
            fnmatch.fnmatch(command, _escape_brackets(pattern)) for pattern in side["commands"]
        ):
            return True
    rel = _path_from_arguments(arguments)
    if rel and any(
        fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(rel.lstrip("./"), pattern)
        for pattern in side["paths"]
    ):
        return True
    return False


def _path(workspace: Path) -> Path:
    return Path(workspace) / ".minicc" / PERMISSIONS_NAME


def load_permission_rules(workspace: Path) -> tuple[dict[str, list[str]], str]:
    """Return (rules, error). Missing file → empty rules, no error."""
    path = _path(workspace)
    key = str(path)
    try:
        stat = path.stat()
    except OSError:
        _cache.pop(key, None)
        return _empty_rules(), ""
    stamp = (stat.st_mtime_ns, stat.st_size)
    with _lock:
        cached = _cache.get(key)
        if cached and cached[0] == stamp:
            return cached[1]
        error = ""
        rules = _empty_rules()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rules, _ = _validate(payload)
        except (OSError, json.JSONDecodeError) as exc:
            error = f"无法读取 {PERMISSIONS_NAME}: {exc}"
        except PermissionConfigError as exc:
            error = f"{PERMISSIONS_NAME} 非法: {exc}"
        if error:
            rules = _empty_rules()
        entry = (rules, error)
        _cache[key] = (stamp, entry)
        return entry


def match_permission_rule(
    workspace: Path, tool: str, arguments: dict[str, Any] | None
) -> str | None:
    """"deny" > "allow" > None. Deny always wins over allow."""
    rules, _error = load_permission_rules(workspace)
    args = arguments if isinstance(arguments, dict) else {}
    if _match_patterns(tool, args, rules["deny"]):
        return "deny"
    if _match_patterns(tool, args, rules["allow"]):
        return "allow"
    return None


__all__ = [
    "PERMISSIONS_NAME",
    "PermissionConfigError",
    "load_permission_rules",
    "match_permission_rule",
]
