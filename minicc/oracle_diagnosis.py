"""Live workspace diagnosis — the model as the on-duty analyst.

The second deep model integration after the workspace brief: the configured
model reads the *measured* interruption / streak / tool / trend evidence of
this workspace and writes the diagnosis no table can hold — the leading cause,
the honest root-cause hypothesis (separating known facts from speculation),
and one concrete next step. Chinese and English, hard JSON contract, same
honesty discipline as the rest of the wire (see ``minicc/oracle_common.py``).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .admin import build_summary
from .config import load_config
from .oracle_common import call_model, cached_zh_en, error_payload, memo_read, memo_write
from .stats import gather

_CACHE_KEY = "oracle-diagnosis:v1"


def _snapshot(workspace: Path) -> dict[str, Any]:
    stats = gather(workspace)
    summary = build_summary(workspace)
    totals = summary.get("totals") or {}
    return {
        "tasks_total": totals.get("tasks"),
        "tasks_completed": totals.get("completed"),
        "tasks_interrupted": totals.get("interrupted"),
        "cache_hit_rate": totals.get("cache_hit_rate"),
        "audit_lines": totals.get("audit_lines"),
        "sessions": totals.get("sessions"),
        "llm_cache_rate": (stats.get("llm_cache") or {}).get("hit_rate"),
        "interrupt_causes": summary.get("interrupt_causes"),
        "completion_streak": summary.get("completion_streak"),
        "tool_usage": (summary.get("tool_usage") or [])[:5],
        "trend_7d": summary.get("trend_7d") or [],
        "recommendations": [
            {"id": rec.get("id"), "priority": rec.get("priority"),
             "title_zh": rec.get("title_zh"), "title_en": rec.get("title_en")}
            for rec in (summary.get("recommendations") or [])
        ],
    }


def _prompt(snapshot: dict[str, Any]) -> str:
    body = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    return (
        "你是本地优先编程工作台 minicc 的值守诊断师。下面 JSON 是这个工作区的实测诊断快照。\n"
        "请写一段诊断（中文 ≤4 句、英文 ≤4 句），按序回答：\n"
        "① 中断主因是什么（引用快照里的数字，明确指出是已知还是推测）；\n"
        "② 最可能的根因假设，并说清楚这是常见模式还是这台机器的特殊情况；\n"
        "③ 现在就能执行的一步；\n"
        "纪律：只引用快照里的数字；快照里没有的事实如实说没有；不许给出“建议……考虑……”这类空话。\n"
        "只返回 JSON：{\"zh\": \"…\", \"en\": \"…\"}\n\n"
        f"快照：{body}"
    )


def build_workspace_diagnosis(*, config: Any | None = None, workspace: Path | None = None,
                              force_refresh: bool = False) -> dict[str, Any]:
    """Return the model-written workspace diagnosis; memoized unless force_refresh."""
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
        call = call_model(config=config, prompt=_prompt(snapshot), max_tokens=380, temperature=0.2)
        diagnosis = cached_zh_en(call["text"])
        payload = {
            "live": True,
            "zh": diagnosis["zh"],
            "en": diagnosis["en"],
            "model": call["model"],
            "usage": call["usage"],
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        memo_write(_CACHE_KEY, payload)
        return payload
    except Exception as exc:  # noqa: BLE001 - the panel shows the outage, honestly
        return error_payload("model-unavailable", exc)
