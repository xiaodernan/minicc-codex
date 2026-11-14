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
import time
from pathlib import Path
from typing import Any

from minicc.agent.protocol import TASK_STATUSES
from minicc.config import home_dir
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


def _store_rows(db_path: Path) -> tuple[list[dict[str, Any]], str | None]:
    try:
        rows = TaskStore(db_path).load(limit=10_000)
        return [row for row in rows if isinstance(row, dict)], None
    except Exception as exc:  # noqa: BLE001 — inventory reports the failure inline
        return [], f"{type(exc).__name__}"


def _normalized_workspace_path(value: Any) -> str | None:
    try:
        return Path(str(value)).resolve().as_posix().lower() if value else None
    except (OSError, ValueError):
        return None


def _workspace_rows(workspace: Path, state: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Merge the workspace store and the shared home store, workspace-scoped.

    The web workbench and CLI both persist tasks — the workbench writes to the
    *home* store (``~/.minicc/tasks.sqlite3``), the workspace store holds only
    workspace-local snapshots. An inventory that reads just one of them
    reports "0 tasks" for a workspace with a hundred. The home rows are
    filtered to this workspace's path, so the merged view stays per-workspace.
    """
    source = {"workspace": 0, "home": 0}
    error: str | None = None
    rows: list[dict[str, Any]] = []
    state_db = state / "tasks.sqlite3"
    if state_db.is_file():
        state_rows, state_err = _store_rows(state_db)
        if state_err:
            error = f"workspace:{state_err}"
        rows += state_rows
        source["workspace"] = len(state_rows)
    try:
        home_db = home_dir() / "tasks.sqlite3"
    except Exception:
        home_db = None
    if home_db is not None and home_db.is_file():
        home_rows, home_err = _store_rows(home_db)
        if home_err:
            error = f"home:{home_err}"
        key = _normalized_workspace_path(workspace)
        picked = [
            row for row in home_rows
            if _normalized_workspace_path(row.get("workspace_path")) == key
        ]
        rows += picked
        source["home"] = len(picked)
    return rows, {"source": source, "error": error}


def _task_stats(state: Path, workspace: Path | None = None) -> dict[str, Any]:
    root = Path(workspace) if workspace is not None else Path.cwd()
    rows, meta = _workspace_rows(root, state)
    counts = {status: 0 for status in sorted(TASK_STATUSES)}
    other = 0
    for row in rows:
        status = str(row.get("status") or "")
        if status in counts:
            counts[status] += 1
        else:
            other += 1
    return {
        "present": (state / "tasks.sqlite3").is_file() or bool(meta["source"]["home"]),
        "total": len(rows),
        "by_status": counts,
        "other": other,
        "source": meta["source"],
        "error": meta["error"],
    }


def _session_stats(root: Path) -> dict[str, Any]:
    try:
        sessions = list_sessions(root)
    except Exception as exc:  # noqa: BLE001 — an unreadable session log is a finding
        detail = f"{type(exc).__name__}: {exc}"
        return {"count": None, "closest": None, "error": detail}
    total_messages = sum(int(item.get("messages") or 0) for item in sessions if item.get("messages") is not None)
    return {"count": len(sessions), "messages": total_messages}


def _llm_cache_stats(state: Path, workspace: Path | None = None) -> dict[str, Any]:
    """Aggregate prompt-cache counters across task snapshots.

    Reads the workspace store and the workspace-matched rows of the shared
    home store (the web-workbench path) — the merged total, summed before
    dividing, exactly as the web metrics payload does it. Rows missing a
    counter contribute nothing; no 0% is ever fabricated.
    """
    root = Path(workspace) if workspace is not None else Path.cwd()
    rows, meta = _workspace_rows(root, state)
    if not (state / "tasks.sqlite3").is_file() and not meta["source"]["home"] and not meta["error"]:
        return {"present": False, "source": meta["source"]}
    hit = 0
    miss = 0
    reported = 0
    for row in rows:
        usage = row.get("tokens_used") if isinstance(row, dict) else None
        if not isinstance(usage, dict):
            continue
        h = usage.get("prompt_cache_hit_tokens")
        m = usage.get("prompt_cache_miss_tokens")
        if isinstance(h, bool) or isinstance(m, bool):
            continue
        if not isinstance(h, (int, float)) or not isinstance(m, (int, float)):
            continue
        if h + m <= 0:
            continue
        hit += int(h)
        miss += int(m)
        reported += 1
    rate = round(hit / (hit + miss), 4) if hit + miss else None
    error = meta["error"]
    out: dict[str, Any] = {
        "present": True,
        "tasks_with_usage": reported,
        "hit_tokens": hit,
        "miss_tokens": miss,
        "hit_rate": rate,
        "source": meta["source"],
    }
    if error:
        out["error"] = error
    return out


_DISK_TTL_SECONDS = 120.0
# Monotonic-clock cache of the "walk .minicc and count bytes" scan. The
# tree routinely holds 322MB in thousands of files and the walk is the
# slowest part of the inventory; every caller polling /api/stats for
# dashboard freshness was paying it back-to-back. Counted bytes change
# slowly; a two-minute answer is honest about being a two-minute answer.
_disk_cache: dict[str, tuple[float, int]] = {}


def _disk_bytes(path: Path) -> int:
    key = str(path)
    now = time.monotonic()
    cached = _disk_cache.get(key)
    if cached is not None:
        at, total = cached
        if now - at < _DISK_TTL_SECONDS:
            return total
    total = 0
    for dirpath, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(dirpath) / name).stat().st_size
            except OSError:
                # A file vanished mid-walk; count what we saw, skip silently.
                continue
    _disk_cache[key] = (now, total)
    return _disk_cache[key][1]


def _cache_stats() -> dict[str, Any]:
    """The Python-side distributed cache view: shared backend vs local LRU fallback."""
    try:
        from minicc.redis_cache import stats
        return stats()
    except Exception as exc:  # noqa: BLE001 — inventory reports the failure inline
        return {"live_backend": None, "local_units": None,
                "local_capacity": None, "error": f"{type(exc).__name__}: {exc}"}


def gather(workspace: Path | str | None = None) -> dict[str, Any]:
    root = Path(workspace) if workspace is not None else Path.cwd()
    state = root / ".minicc"
    state_exists = state.is_dir()
    return {
        "workspace": root.as_posix(),
        "state_dir_present": state_exists,
        "audit": _audit_stats(state),
        "tasks": _task_stats(state, root),
        "sessions": _session_stats(root),
        "disk_bytes": _disk_bytes(state) if state_exists else 0,
        "cache": _cache_stats(),
        "llm_cache": _llm_cache_stats(state, root),
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
        source = tasks.get("source") or {}
        src = f" [workspace {source.get('workspace', 0)} / home {source.get('home', 0)}]"
        counts = " ".join(f"{s}={n}" for s, n in tasks["by_status"].items())
        lines.append(f"tasks: {tasks['total']} total ({counts}) other={tasks['other']}{src}")
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

    llm = report.get("llm_cache") or {}
    if llm.get("error"):
        lines.append(f"llm cache: store unreadable ({llm['error']})")
    elif not llm.get("present"):
        lines.append("llm cache: absent")
    elif not llm.get("tasks_with_usage"):
        lines.append("llm cache: no cache counters in stored tasks")
    else:
        rate = llm.get("hit_rate")
        rate_text = f"{rate * 100:.1f}%" if isinstance(rate, (int, float)) else "n/a"
        lines.append(
            f"llm cache: {llm['tasks_with_usage']} tasks, hit rate {rate_text} "
            f"(hit {llm['hit_tokens']}, miss {llm['miss_tokens']})"
        )

    cache = report.get("cache") or {}
    if cache.get("error"):
        lines.append(f"cache: {cache['error']}")
    else:
        live = "live" if cache.get("live_backend") else "local"
        units = cache.get("local_units")
        capacity = cache.get("local_capacity")
        if cache.get("live_backend") is None:
            lines.append("cache: unavailable")
        else:
            lines.append(f"cache: {live} (local units {units}/{capacity}, gets={cache.get('gets',0)}, sets_shared={cache.get('sets_shared',0)}, sets_local={cache.get('sets_local',0)})")
    return "\n".join(lines)
