"""Live completion-assurance — the model judges the last 'completed' task's claim.

You already have the judge for the live loop (minicc/agent/completion.py). This
is the admin panel's mirror of the same duty: the record of the most recent task
that declared itself completed, read back out of the audit journal. The model
never sees a tool call it cannot look up in that record; it verdicts only on
plausibility and on the one check that would settle the matter.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .admin import build_summary
from .config import load_config
from .oracle_common import call_model, cached_zh_en, error_payload, memo_read, memo_write

_CACHE_KEY = "oracle-retrospective:v1"


def _snapshot(workspace: Path) -> dict[str, Any]:
    summary = build_summary(workspace)
    recent = summary.get("recent_tasks") or []
    # Prefer the completed one: what this tile judges is the claim "this is done".
    last_completed = next((row for row in recent if str(row.get("status")) == "completed"), None)
    totals = summary.get("totals") or {}
    return {
        "tasks_total": totals.get("tasks"),
        "tasks_completed": totals.get("completed"),
        "tasks_interrupted": totals.get("interrupted"),
        "interrupted_causes": summary.get("interrupt_causes"),
        "cache_hit_rate": totals.get("cache_hit_rate"),
        "audit_lines": totals.get("audit_lines"),
        "completion_streak": summary.get("completion_streak"),
        "last_task": {
            "id": last_completed["id"] if last_completed else None,
            "preview": last_completed["message"] if last_completed else None,
            "phase": last_completed["phase"] if last_completed else None,
            "age_hours": last_completed["age_hours"] if last_completed else None,
        },
        "other_recent": [
            {k: row.get(k) for k in ("id", "status", "preview", "phase", "age_hours")}
            for row in recent[:4] if str(row.get("status")) != "completed"
        ],
    }


def _prompt(snapshot: dict[str, Any]) -> str:
    body = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    return (
        "你是 minicc 值守的事后复核员。下面 JSON 是这个工作区的实测快照。\n"
        "请针对“最近一个声称自己完成的任务”写一段事后复核（中文 ≤4 句、英文 ≤4 句）：\n"
        "① 这个任务可信度如何（引用快照里的 preview/phase/状态数字）；\n"
        "② 如果可信，凭什么快速复验；如果含糊，最坏情况下会出什么问题；\n"
        "③ 明天（或下一轮）你应该先做的一步——只写一个，且要有验收方式。\n"
        "如果没有任何任务声称自己完成，如实写“最近没有完成的任务”。\n"
        "只返回 JSON：{\"zh\": \"…\", \"en\": \"…\"}\n\n"
        f"快照：{body}"
    )


def build_workspace_retrospective(*, config: Any | None = None, workspace: Path | None = None,
                                   force_refresh: bool = False) -> dict[str, Any]:
    """Return the model-written retrospective; memoized unless force_refresh."""
    if not force_refresh:
        cached = memo_read(_CACHE_KEY)
        if isinstance(cached, dict) and cached.get("live") is not None:
            return cached

    root = Path(workspace) if workspace is not None else Path.cwd()
    if config is None:
        try:
            config = load_config(workspace=root)
        except Exception as exc:  # noqa: BLE001 - surface the outage, never 500
            return error_payload("config-unavailable", exc)

    try:
        snapshot = _snapshot(root)
    except Exception as exc:  # noqa: BLE001 - a partial snapshot is reported, not raised
        return error_payload("snapshot-unavailable", exc)

    try:
        call = call_model(config=config, prompt=_prompt(snapshot), max_tokens=360, temperature=0.15)
        review = cached_zh_en(call["text"])
        payload = {
            "live": True,
            "zh": review["zh"],
            "en": review["en"],
            "model": call["model"],
            "usage": call["usage"],
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        memo_write(_CACHE_KEY, payload)
        return payload
    except Exception as exc:  # noqa: BLE001 - the panel shows the outage, honestly
        return error_payload("model-unavailable", exc)
