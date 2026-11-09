"""``minicc --stats``: a read-only operational inventory of the current workspace.

The doctor answers "is this workspace healthy?"; the stats surface answers
"what does it currently hold?".  Neither calls the network nor the model nor
the suite.  Statistics are reported from the files the product itself writes;
when one of them is unreadable the probe reports the failure inline instead
of dying on it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from minicc.agent.protocol import TASK_STATUSES
from minicc.internal_paths import AUDIT_NAME
from minicc.session import list_sessions
from minicc.task_store import TaskStore


def _audit_stats(state: Path) -> dict[str, Any]:
    audit = state / AUDIT_NAME
    if not audit.is_file():
        return {"present": False, "lines": None, "last_event": None}
    try:
        lines = audit.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        # An unreadable audit log is a finding, not a crash.
        reason = f"unreadable: {type(exc).__name__}"
        return {"present": True, "lines": None, "last_event": reason}
    last_event: Any = None
    for line in reversed(lines):
        entry = line.strip()
        if not entry:
            continue
        try:
            payload = json.loads(entry)
        except ValueError:
            last_event = "<unparseable audit line>"
            break
        if isinstance(payload, dict):
            last_event = payload.get("event") or payload.get("type") or payload.get("kind")
        else:
            last_event = "<audit line is not an object>"
        break
    return {"present": True, "lines": len(lines), "last_event": last_event}


def _task_stats(state: Path) -> dict[str, Any]:
    db = state / "tasks.sqlite3"
    out: dict[str, Any] = {"present": db.is_file(), "total": 0,
                           "by_status": {status: 0 for status in sorted(TASK_STATUSES)}, "other": 0}
    if not db.is_file():
        return out
    try:
        store = TaskStore(db)
        rows = store.load(limit=10_000)
    except Exception as exc:  # noqa: BLE001 — inventory reports the failure inline
        detail = f"{type(exc).__name__}"
        return {**out, "error": detail}
    counts = {status: 0 for status in sorted(TASK_STATUSES)}
    other = 0
    for row in rows:
        status = str(row.get("status") or "")
        if status in counts:
            counts[status] += 1
        else:
            other += 1
    out["total"] = len(rows)
    out["by_status"] = counts
    out["other"] = other
    return out


def _session_stats(root: Path) -> dict[str, Any]:
    try:
        sessions = list_sessions(root)
    except Exception as exc:  # noqa: BLE001 — an unreadable session log is a finding
        detail = f"{type(exc).__name__}: {exc}"
        return {"count": None, "closest": None, "error": detail}
    total_messages = sum(int(item.get("messages") or 0) for item in sessions if item.get("messages") is not None)
    return {"count": len(sessions), "messages": total_messages}


def _disk_bytes(path: Path) -> int:
    total = 0
    for dirpath, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(dirpath) / name).stat().st_size
            except OSError:
                # A file vanished mid-walk; count what we saw, skip silently.
                continue
    return total


def gather(workspace: Path | str | None = None) -> dict[str, Any]:
    root = Path(workspace) if workspace is not None else Path.cwd()
    state = root / ".minicc"
    state_exists = state.is_dir()
    return {
        "workspace": root.as_posix(),
        "state_dir_present": state_exists,
        "audit": _audit_stats(state),
        "tasks": _task_stats(state),
        "sessions": _session_stats(root),
        "disk_bytes": _disk_bytes(state) if state_exists else 0,
    }


def format_stats(report: dict[str, Any], *, json_out: bool = False) -> str:
    if json_out:
        return json.dumps(report, ensure_ascii=False)
    lines = [f"minicc stats — workspace {report['workspace']}"]
    lines.append(f"state: {'present' if report['state_dir_present'] else 'absent'} (.minicc/, {report['disk_bytes']} bytes)")

    audit = report["audit"]
    if audit["present"]:
        lines.append(f"audit: {audit['lines']} lines, last event {audit['last_event']!r}")
    else:
        lines.append("audit: absent")

    tasks = report["tasks"]
    if tasks["present"]:
        counts = " ".join(f"{s}={n}" for s, n in tasks["by_status"].items())
        lines.append(f"tasks: {tasks['total']} total ({counts}) other={tasks['other']}")
        if tasks.get("error"):
            lines.append(f"tasks store: unreadable ({tasks['error']})")
    else:
        lines.append("tasks: absent (no tasks.sqlite3)")

    sessions = report["sessions"]
    if sessions.get("error"):
        lines.append(f"sessions: {sessions['error']}")
    elif sessions["count"] is None:
        lines.append("sessions: unreadable")
    else:
        lines.append(f"sessions: {sessions['count']} stored, {sessions['messages']} messages")
    return "\n".join(lines)
