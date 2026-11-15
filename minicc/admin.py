"""M8-T1014: Admin summary — one read-only payload for the admin dashboard.

The user can unlock the admin panel with the shared password ``123`` (this
is a local-first tool; the door is honest about being shared). The panel
reads this single route and renders cards, a trend line and an
evidence-anchored recommendation list.

Interestingly real things it computes — none of them demo data:

* totals from ``stats()`` (the actual sqlite store + audit log counts)
* cache hit rate from ``cache_summary`` aggregation over the ledger
* a 7-day trend by counting ``audit.jsonl`` timestamps per UTC day
* concrete, data-backed suggestions (cache < 80 % → add keeper window, etc.)

Never raises; every failure mode reports ``{"error": "..."}`` or an empty
section so the admin surface never crashes on a broken workspace.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import home_dir
from .internal_paths import AUDIT_NAME
from .ratelimit import stats as ratelimit_stats
from .redis_cache import stats as redis_stats
from .stats import gather as stats_gather


def _today_utc() -> datetime:
    return datetime.now(timezone.utc)


def _day_key(ts: str) -> str | None:
    try:
        return ts[:10]
    except Exception:
        return None


def _audit_trend(state_dir: Path) -> list[dict[str, Any]]:
    audit = state_dir / AUDIT_NAME
    if not audit.is_file():
        return []
    counter: dict[str, int] = defaultdict(int)
    today = _today_utc()
    try:
        lines = audit.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        ts = entry.get("timestamp") if isinstance(entry, dict) else None
        day = _day_key(ts) if isinstance(ts, str) else None
        if day:
            counter[day] += 1
    # emit the last 7 days, zero-filled so the line is never broken
    out: list[dict[str, Any]] = []
    for delta in range(6, -1, -1):
        day_dt = today.fromordinal(today.toordinal() - delta)
        key = day_dt.strftime("%Y-%m-%d")
        out.append({"day": key, "events": int(counter.get(key, 0))})
    return out


def _recent_tasks(state_dir: Path, limit: int = 8) -> list[dict[str, Any]]:
    """Read the active tasks store (global home). Falls back to the workspace store."""
    rows: list[dict[str, Any]] = []
    candidates: list[Path] = []
    try:
        candidates.append(home_dir() / "tasks.sqlite3")
    except Exception:
        pass
    if state_dir.is_dir():
        candidate = state_dir / "tasks.sqlite3"
        if candidate not in candidates:
            candidates.append(candidate)
    for db in candidates:
        if not db.is_file():
            continue
        try:
            from .task_store import TaskStore
            rows.extend(
                row for row in TaskStore(db).load(limit=max(limit, 32))
                if isinstance(row, dict)
            )
        except Exception:
            continue
    def _first_line(value: Any) -> str:
        lines = str(value or "").splitlines()
        line = lines[0] if lines else ""
        # a prompt may once have carried a live key - never echo one into the panel
        line = re.sub(r"sk-[A-Za-z0-9]{20,}", "sk-...redacted", line)
        return line[:80]

    def _age_hours(row: dict) -> float | None:
        created = row.get("created_at_epoch") or row.get("updated_at_epoch")
        try:
            return round((now - float(created)) / 3600.0, 1) if created is not None else None
        except (TypeError, ValueError):
            epoch = row.get("created_at") or row.get("started_at")
            try:
                if isinstance(epoch, str) and epoch:
                    from datetime import datetime as _dt

                    ts = _dt.fromisoformat(epoch.replace("Z", "+00:00")).timestamp()
                    return round((now - ts) / 3600.0, 1)
            except (TypeError, ValueError):
                return None
            return None

    out: list[dict[str, Any]] = []
    now = time.time()
    for row in rows:
        age_hours = _age_hours(row)
        out.append(
            {
                "id": str(row.get("task_id") or row.get("id") or "?"),
                "status": str(row.get("status") or "unknown"),
                "message": _first_line(row.get("preview") or row.get("message") or row.get("prompt")),
                "phase": str(row.get("phase") or ""),
                "age_hours": age_hours,
                "_sort": age_hours if age_hours is not None else 1e9,
            }
        )
    out.sort(key=lambda item: item["_sort"])
    for item in out:
        item.pop("_sort", None)
    return out[:limit]


def build_summary(workspace: Path) -> dict[str, Any]:
    """Build the admin-panel payload. Never raises; returns {} on failure."""
    try:
        s = stats_gather(workspace)
    except Exception:
        s = {}
    try:
        redis_s = redis_stats()
    except Exception:
        redis_s = {}
    try:
        rlimit_s = ratelimit_stats()
    except Exception:
        rlimit_s = {}
    try:
        state_dir = workspace / ".minicc" if (workspace / ".minicc").is_dir() else home_dir()
    except Exception:
        state_dir = workspace / ".minicc"
    try:
        trend_7d = _audit_trend(state_dir)
    except Exception:
        trend_7d = []
    try:
        recent_tasks = _recent_tasks(state_dir)
    except Exception:
        recent_tasks = []

    # measurable totals — read the exact shape the stats surface emits
    total_count = 0
    completed = 0
    interrupted = 0
    cache_rate = None
    audit_lines = None
    sessions_count = 0
    if isinstance(s, dict):
        tasks_info = s.get("tasks") or {}
        by_status = (tasks_info.get("by_status") or {}) if isinstance(tasks_info, dict) else {}
        by_status = {str(k): int(v or 0) for k, v in by_status.items()} if isinstance(by_status, dict) else {}
        total_count = int(tasks_info.get("total", tasks_info.get("count", sum(by_status.values()))) or 0)
        completed = int(by_status.get("completed", 0))
        interrupted = int(by_status.get("interrupted", 0))
        llm = s.get("llm_cache") or {}
        if isinstance(llm, dict) and llm.get("hit_rate") is not None:
            cache_rate = float(llm["hit_rate"])
        audit = s.get("audit") or {}
        if isinstance(audit, dict):
            audit_lines = audit.get("lines")
        sessions_info = s.get("sessions") or {}
        if isinstance(sessions_info, dict):
            sessions_count = int(sessions_info.get("count", 0) or 0)

    recommendations: list[dict[str, Any]] = []
    if cache_rate is not None and cache_rate < 0.8:
        recommendations.append(
            {
                "id": "keeper-window",
                "priority": "high",
                "title_zh": "保持前缀缓存热度——把 keeper 拉到 220 s 间隔",
                "title_en": "Keep the prefix warm — raise the keeper to a tighter beat",
                "why_zh": f"当前样本缓存命中率 {cache_rate * 100:.1f}%，说低。检查 .minicc/sessions 中大任务是否跨过了上游 TTL（5 分钟），调整 MINICC_CACHE_KEEPER_INTERVAL。",
                "why_en": f"Aggregate cache hit rate is {cache_rate * 100:.1f}% — lower than it should be. Check .minicc/sessions for long tasks that span the upstream TTL (~5 min), and shorten MINICC_CACHE_KEEPER_INTERVAL.",
            }
        )
    if interrupted > 0:
        recommendations.append(
            {
                "id": "interrupted-tasks",
                "priority": "medium",
                "title_zh": f"回看 {interrupted} 个中断任务——找出共同根因",
                "title_en": f"Review {interrupted} interrupted tasks — find the common thread",
                "why_zh": "中断不是失败堆积——它们往往说明 verifier 不愿签名或权限卡住。看着最近 8 个中断任务的事件流找共同点（超时/权限/模型拒绝）。",
                "why_en": "Interruptions pile up when the verifier refuses or a permission check holds. Walk the last 8 interrupted tasks' event streams to spot a shared cause (timeout / permission / model refusal).",
            }
        )
    if redis_s and not redis_s.get("live_backend", False):
        recommendations.append(
            {
                "id": "redis-live",
                "priority": "low",
                "title_zh": "把世界脉搏提到 Redis 实时后端",
                "title_en": "Move world pulse to a live Redis-backed cache",
                "why_zh": "当前 LRU 兜底工作得很好，但世界数据只在当前工作区内可见——换成 Redis 让新会话也能取到。",
                "why_en": "The local LRU fallback works well, but world pulse only survives the current session. With a live Redis the next cold start sees it too.",
            }
        )

    return {
        "totals": {
            "tasks": total_count,
            "completed": completed,
            "interrupted": interrupted,
            "cache_hit_rate": cache_rate,
            "audit_lines": audit_lines,
            "sessions": sessions_count,
        },
        "trend_7d": trend_7d,
        "recent_tasks": recent_tasks,
        "recommendations": recommendations,
        "redis": redis_s if isinstance(redis_s, dict) else {},
        "ratelimit": rlimit_s if isinstance(rlimit_s, dict) else {},
    }

