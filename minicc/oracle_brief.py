"""Live workspace brief — the model on duty for this workspace.

A deep, on-demand integration: the configured model reads the *measured*
fact pack of this workspace (git-derived digest, task store summary, 7-day
events trend) and writes a two-part (zh + en) brief for whoever just opened
the admin panel. The model sees no secrets — only the counters and dates a
visitor of the panel may already read — and answers with a hard JSON
contract so the panel never paints an unparsable page.

Discipline matched to the rest of the product — see ``minicc/oracle_common.py``
for the shared plumbing (one home per wire: stability, usage accounting and
honest fallbacks); this module is only the brief's own shape.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .admin import build_summary
from .config import load_config
from .digest import build_digest
from .oracle_common import call_model, cached_zh_en, error_payload, memo_read, memo_write
from .stats import gather

_CACHE_KEY = "oracle-brief:v1"


def _snapshot(workspace: Path) -> dict[str, Any]:
    digest = build_digest(workspace)
    stats = gather(workspace)
    summary = build_summary(workspace)
    totals = summary.get("totals") or {}
    return {
        "head_short": digest.get("head_short"),
        "branch": digest.get("branch"),
        "total_commits": digest.get("total_commits"),
        "almanac_chapters": digest.get("almanac_chapters"),
        "roadmap_batches": digest.get("roadmap_batches"),
        "tracked_files": digest.get("tracked_files"),
        "test_files": digest.get("test_files"),
        "first_commit_at": digest.get("first_commit_at"),
        "tasks_total": totals.get("tasks"),
        "tasks_completed": totals.get("completed"),
        "tasks_interrupted": totals.get("interrupted"),
        "cache_hit_rate": totals.get("cache_hit_rate"),
        "audit_lines": totals.get("audit_lines"),
        "sessions": totals.get("sessions"),
        "llm_cache_rate": (stats.get("llm_cache") or {}).get("hit_rate"),
        "trend_7d": summary.get("trend_7d") or [],
        "top_tools": (summary.get("tool_usage") or [])[:5],
    }


def _prompt(snapshot: dict[str, Any]) -> str:
    body = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    return (
        "你是本地优先编程工作台 minicc 的值守分析师。下面 JSON 是这个工作区的实测快照。\n"
        "请为刚打开管理员面板的人写一段工作区简报：中文 3 句以内，英文 3 句以内。\n"
        "纪律：只引用快照里的数字，绝不编造；数字紧随句后；快照里没有的东西，两种语言都如实写没有。\n"
        "只返回 JSON，不要额外正文：{\"zh\": \"…\", \"en\": \"…\"}\n\n"
        f"快照：{body}"
    )


def build_workspace_brief(*, config: Any | None = None, workspace: Path | None = None,
                          force_refresh: bool = False) -> dict[str, Any]:
    """Return the model-written workspace brief; memoized unless force_refresh."""
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
        call = call_model(config=config, prompt=_prompt(snapshot), max_tokens=280, temperature=0.2)
        brief = cached_zh_en(call["text"])
        payload = {
            "live": True,
            "zh": brief["zh"],
            "en": brief["en"],
            "model": call["model"],
            "usage": call["usage"],
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        memo_write(_CACHE_KEY, payload)
        return payload
    except Exception as exc:  # noqa: BLE001 - the panel shows the outage, honestly
        return error_payload("model-unavailable", exc)
