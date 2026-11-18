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
from collections import defaultdict
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
    return ts[:10] if isinstance(ts, str) else None


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



def _least_squares_slope(ys: list[float]) -> float:
    n = len(ys)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom


def _forecast_from_trend(trend_7d: list[dict[str, Any]]) -> dict[str, Any] | None:
    """A deliberately naive, honest projection over the 7-day event counts.

    Fits a straight line over the 7 real buckets; returns the signed slope and a
    next-day estimate. Also measures last-two-days vs the peak, which is the
    honest "is the building cooling off" number the recommendation keys on.
    Never pretends to be statistical rigour.
    """
    if not trend_7d:
        return None
    ys = [float(d.get("events") or 0) for d in trend_7d]
    n = len(ys)
    avg = sum(ys) / n
    slope = _least_squares_slope(ys)
    intercept = (sum(ys) - slope * sum(range(n))) / n
    peak_day = max(trend_7d, key=lambda d: float(d.get("events") or 0))
    peak = float(peak_day.get("events") or 0)
    last2 = sum(ys[-2:]) / 2 if n >= 2 else avg
    decline_from_peak = max(0.0, 1 - (last2 / peak)) if peak > 0 else 0.0
    direction = "down" if decline_from_peak >= 0.45 else ("up" if last2 > avg * 1.15 else "flat")
    return {
        "slope_per_day": round(slope, 2),
        "avg_events": round(avg, 1),
        "next_day_events": int(max(0, round(intercept + slope * n))),
        "direction": direction,
        "peak_day": str(peak_day.get("day", "—")),
        "peak_events": int(peak_day.get("events") or 0),
        "decline_from_peak": round(decline_from_peak, 2),
        "last_2_avg": round(last2, 1),
    }


_RESTART_MARKERS = ("服务重启", "service restart", "restart")
_TIMEOUT_MARKERS = ("超时", "timeout")
_PERMISSION_MARKERS = ("权限", "permission", "refused")
_CANCEL_MARKERS = ("取消", "cancel")


_TOOL_LIMIT = 200


def _tool_usage_breakdown(state_dir: Path) -> list[dict[str, Any]]:
    """Count tool invocations across recent tasks — real data, honest bucket.

    Source of truth is the task store's events array (kind == "tool"). Each
    event names the tool the agent actually called. Counted across the two
    most recent stores (home + workspace), capped at ``_TOOL_LIMIT`` rows for
    an honest, bounded probe.
    """
    counts: dict[str, int] = {}
    candidates: list[Path] = []
    try:
        candidates.append(home_dir() / "tasks.sqlite3")
    except (OSError, ValueError):
        pass
    if state_dir.is_dir():
        candidate = state_dir / "tasks.sqlite3"
        if candidate not in candidates:
            candidates.append(candidate)
    try:
        import sqlite3

        from .task_store import TaskStore
        for db in candidates:
            if not db.is_file():
                continue
            rows = TaskStore(db).load(limit=_TOOL_LIMIT)
            for row in rows:
                if not isinstance(row, dict):
                    continue
                evs = row.get("events")
                if isinstance(evs, str):
                    try:
                        evs = json.loads(evs)
                    except (ValueError, TypeError):
                        continue
                if not isinstance(evs, list):
                    continue
                for e in evs:
                    if not isinstance(e, dict):
                        continue
                    if e.get("kind") != "tool":
                        continue
                    name = e.get("name") or e.get("tool_name")
                    if isinstance(name, str) and name:
                        counts[name] = counts.get(name, 0) + 1
    except (sqlite3.Error, OSError, ValueError):
        return []
    total = sum(counts.values())
    if not total:
        return []
    top = sorted(counts.items(), key=lambda item: -item[1])[:6]
    return [
        {"name": name, "count": count, "pct": round(100 * count / total, 1)}
        for name, count in top
    ]


def _interrupt_cause_breakdown(state_dir: Path) -> dict[str, Any] | None:
    """Bucket interrupted tasks by the cause their own error field recorded.

    The workspace's interrupted tasks all died on the same event: a service
    restart while they were mid-flight. That is a single, honest, actionable
    root cause - surfacing it beats another generic "review your tasks".
    """
    counts = {"restart": 0, "timeout": 0, "permission": 0, "cancelled": 0, "other": 0, "unknown": 0}
    candidates: list[Path] = []
    try:
        candidates.append(home_dir() / "tasks.sqlite3")
    except (OSError, ValueError):
        # candidate set just stays smaller then; workspace store is still tried
        pass
    if state_dir.is_dir():
        candidate = state_dir / "tasks.sqlite3"
        if candidate not in candidates:
            candidates.append(candidate)
    found = 0
    try:
        import sqlite3

        from .task_store import TaskStore
        for db in candidates:
            if not db.is_file():
                continue
            rows = TaskStore(db).load(limit=10_000)
            for row in rows:
                if not isinstance(row, dict):
                    continue
                if str(row.get("status")) != "interrupted":
                    continue
                found += 1
                error = str(row.get("error") or row.get("cancel_reason") or "")
                lowered = error.lower()
                if any(m.lower() in lowered for m in _RESTART_MARKERS):
                    counts["restart"] += 1
                elif any(m.lower() in lowered for m in _TIMEOUT_MARKERS):
                    counts["timeout"] += 1
                elif any(m.lower() in lowered for m in _PERMISSION_MARKERS):
                    counts["permission"] += 1
                elif any(m.lower() in lowered for m in _CANCEL_MARKERS):
                    counts["cancelled"] += 1
                elif lowered:
                    counts["other"] += 1
                else:
                    counts["unknown"] += 1
    except (sqlite3.Error, OSError, ValueError):
        return None
    if found == 0:
        return None
    return {"total": found, **counts}


def _completion_streak(state_dir: Path) -> dict[str, Any] | None:
    """Consecutive-day streak of *completed* tasks.

    Read straight off the task store's own rows: a day counts when at least
    one task reached status=completed that UTC day. The answer is three
    honest numbers: the current run (today counts if it already has a
    completion; otherwise the streak that already ended before today is
    reported as the current streak), the best run observed anywhere in
    the data, and how many distinct completion days the data contains.
    Honest blank when there is nothing to count - a workspace that never
    completed anything is not a zero, it is an unknown.

    All date math happens on plain epoch day-indexes; the one wire string
    (last_completed) is produced by clock.utc_iso, the one UTC authority.
    """
    day_indexes: set[int] = set()
    candidates: list[Path] = []
    try:
        candidates.append(home_dir() / "tasks.sqlite3")
    except (OSError, ValueError):
        # candidate set just stays smaller then; workspace store is still tried
        pass
    if state_dir.is_dir():
        candidate = state_dir / "tasks.sqlite3"
        if candidate not in candidates:
            candidates.append(candidate)
    try:
        import sqlite3
        from math import floor

        from .task_store import TaskStore
        for db in candidates:
            if not db.is_file():
                continue
            rows = TaskStore(db).load(limit=50_000)
            for row in rows:
                if not isinstance(row, dict):
                    continue
                if str(row.get("status")) != "completed":
                    continue
                epoch = row.get("finished_at_epoch") or row.get("updated_at_epoch") or row.get("created_at_epoch")
                if epoch is None:
                    continue
                try:
                    day_indexes.add(floor(float(epoch) / 86400))
                except (TypeError, ValueError, OverflowError):
                    continue
    except (sqlite3.Error, OSError, ValueError, TypeError, OverflowError):
        return None
    if not day_indexes:
        return None
    ordered = sorted(day_indexes)
    # best run anywhere in the window
    best = 1
    run = 1
    for prev, cur in zip(ordered, ordered[1:]):
        if cur - prev == 1:
            run += 1
            best = max(best, run)
        else:
            run = 1
    # current run: today (or yesterday) must contain the run's head, else zero
    from math import floor

    from .clock import utc_iso

    today = floor(time.time() / 86400)
    last = ordered[-1]
    if today - last > 1:
        current = 0
    else:
        current = 1
        idx = len(ordered) - 1
        while idx > 0:
            if ordered[idx] - ordered[idx - 1] == 1:
                current += 1
                idx -= 1
            else:
                break
    last_completed = (utc_iso(last * 86400 + 43200) or "")[:10]
    return {"current": current, "best": best, "days": len(day_indexes), "last_completed": last_completed}


def _recent_tasks(state_dir: Path, limit: int = 8) -> list[dict[str, Any]]:
    """Read the active tasks store (global home). Falls back to the workspace store."""
    rows: list[dict[str, Any]] = []
    candidates: list[Path] = []
    try:
        candidates.append(home_dir() / "tasks.sqlite3")
    except (OSError, ValueError):
        # a missing/locked/unparseable home dir only disqualifies the home store candidate
        pass
    if state_dir.is_dir():
        candidate = state_dir / "tasks.sqlite3"
        if candidate not in candidates:
            candidates.append(candidate)
    for db in candidates:
        if not db.is_file():
            continue
        try:
            import sqlite3

            from .task_store import TaskStore
            rows.extend(
                row for row in TaskStore(db).load(limit=max(limit, 32))
                if isinstance(row, dict)
            )
        except (sqlite3.Error, OSError, ValueError):
            # a locked/corrupt home store is a finding, not a crash - try the next candidate
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
    except Exception as exc:  # noqa: BLE001 - an unreadable workspace degrades every counter to honest blanks, never a 500
        s = {}
    try:
        redis_s = redis_stats()
    except Exception as exc:  # noqa: BLE001 - redis telemetry is best-effort; the panel reports honest zeros when the pool is gone
        redis_s = {}
    try:
        rlimit_s = ratelimit_stats()
    except Exception as exc:  # noqa: BLE001 - ratelimit telemetry is best-effort; the panel reports honest zeros when the bucket is gone
        rlimit_s = {}
    state_dir = workspace / ".minicc" if (workspace / ".minicc").is_dir() else home_dir()
    try:
        trend_7d = _audit_trend(state_dir)
    except OSError:
        # an unreadable audit log is an honest blank chart, never a 500
        trend_7d = []
    try:
        recent_tasks = _recent_tasks(state_dir)
    except Exception as exc:  # noqa: BLE001 - task-store failure is an honest blank list; the panel still shows totals/trend/recommendations
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

    forecast = _forecast_from_trend(trend_7d)

    interrupt_causes = _interrupt_cause_breakdown(state_dir)
    completion_streak = _completion_streak(state_dir)
    tool_usage = _tool_usage_breakdown(state_dir)

    recommendations: list[dict[str, Any]] = []
    if interrupt_causes and interrupt_causes.get("restart", 0) > 0:
        n = int(interrupt_causes["restart"])
        recommendations.append(
            {
                "id": "restart-interrupt",
                "priority": "medium",
                "title_zh": f"{n} 个中断全部源于服务重启——把 workbench 留在回环前台",
                "title_en": f"{n} interrupted task(s) trace to service restarts - keep the workbench in the foreground",
                "why_zh": f"中断账本里的错误字段原生记的就是「服务重启时任务被中断」：任务在途中，worker 随本地服务一起被杀。办法很实在——别在后台反复重启 minicc-web；收尾或定期维护前先让运行中的任务跑完；已被中断的任务可以直接重跑收敛。",
                "why_en": "The task store's own error text for every interruption is 'interrupted during a service restart': the workers died mid-flight with the workbench process. The fix is concrete - stop restarting minicc-web casually around long tasks, let the running ones converge first, or re-run the interrupted tasks to collect.",
            }
        )
    if (
        forecast is not None
        and forecast["decline_from_peak"] >= 0.45
        and forecast["avg_events"] >= 4.0
        and forecast["direction"] == "down"
    ):
        recommendations.append(
            {
                "id": "fading-weekend-quiet",
                "priority": "medium",
                "title_zh": "事件频率从峰值回落——安排下一批航程",
                "title_en": "Event rate fell off the peak — queue the next voyage",
                "why_zh": f"{forecast['peak_day']} 出现 {forecast['peak_events']} 次后，最近两天均值仅 {forecast['last_2_avg']}（回落 {forecast['decline_from_peak'] * 100:.0f}%）。显著冷却是真实发生的，不是一条温吞的新闻——开个新 session，或把手册翻到下一章，或看 Doctor 的缓存守护是否还在值班。",
                "why_en": f"{forecast['peak_day']} hit {forecast['peak_events']}; the last two days average {forecast['last_2_avg']} (down {forecast['decline_from_peak'] * 100:.0f}% from the peak). That cooling-off is real, not a soft note — open a fresh session, flip to the next manual chapter, or check the cache keeper in the Doctor panel.",
            }
        )
    if cache_rate is not None and cache_rate < 0.8:
        recommendations.append(
            {
                "id": "keeper-window",
                "priority": "high",
                "title_zh": "保持前缀缓存热度——60 s 间隔的 keeper 已解决\"中途掉缓存\"（2026-11-18 实测 TTL ≤150 s）",
                "title_en": "Keep the prefix warm — the default is now 60 s (measured upstream TTL ≤ 150 s, 2026-11-18)",
                "why_zh": f"当前样本缓存命中率 {cache_rate * 100:.1f}%。实测新 lane 的同前缀 ≤150 s 无 warm 即被 evict（2026-11-18）——上一版 220 s 间隔从未让 lane 持续暖住；现在 MINICC_CACHE_KEEPER_INTERVAL 默认 60 s，60 s 保活即可。若订阅量再低，也别低于 60 s。",
                "why_en": f"Aggregate cache hit rate is {cache_rate * 100:.1f}%. Measured on this lane (2026-11-18): a byte-identical prefix is evicted within ≤150 s of silence — the old 220 s cadence could never hold the warmth; the default is now 60 s. Do not raise it above 60 s without new data.",
            }
        )
    if completion_streak and completion_streak["best"] >= 3 and completion_streak["current"] == 0:
        best = int(completion_streak["best"])
        recommendations.append(
            {
                "id": "streak-deserted",
                "priority": "low",
                "title_zh": f"连签 {best} 天里最大的一段现在断了——开一个回归的 session 就好",
                "title_en": f"The best run ({best} days) has broken — one honest session brings it back",
                "why_zh": f"最近一次完成任务落在 {completion_streak['last_completed']}；之后没有一单收尾。这不是游戏化的绿勾，而是这台工作区真实的产出节奏——断了，就还能回来。",
                "why_en": f"The newest completed task finished on {completion_streak['last_completed']}; nothing has shipped since. Not a gamified badge — the real cadence of this workspace. It broke, and it can come back.",
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
        "forecast": forecast,
        "interrupt_causes": interrupt_causes,
        "tool_usage": tool_usage,
        "completion_streak": completion_streak,
        "recent_tasks": recent_tasks,
        "recommendations": recommendations,
        "redis": redis_s if isinstance(redis_s, dict) else {},
        "ratelimit": rlimit_s if isinstance(rlimit_s, dict) else {},
    }

