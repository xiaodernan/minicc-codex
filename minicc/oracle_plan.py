"""Live 'first three moves' — the model writes the ordered priorities for this workspace.

Third model duty: not a summary of what happened, not a post-mortem of what broke —
the three concrete next moves this workspace should make, each with one acceptance
check. Always grounded in the measured snapshot; never generic motivational text.
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

_CACHE_KEY = "oracle-plan:v1"


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
        "llm_cache_rate": (stats.get("llm_cache") or {}).get("hit_rate"),
        "sessions": totals.get("sessions"),
        "interrupt_causes": summary.get("interrupt_causes"),
        "completion_streak": summary.get("completion_streak"),
        "tool_usage": (summary.get("tool_usage") or [])[:6],
        "trend_7d": summary.get("trend_7d") or [],
        "recommendations": summary.get("recommendations") or [],
    }


def _prompt(snapshot: dict[str, Any]) -> str:
    body = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    return (
        "你是本地优先编程工作台 minicc 的值守规划师。下面 JSON 是这个工作区的实测快照。\n"
        "请写三件这台工作区现在应该做的具体事，按优先级排序（第一件最紧急）。\n"
        "技术纪律：只引用快照里的数字；禁止“优化、改进、考察、调研”这类没有落锚点的词；每件事必须有（1）一句具体的行动，（2）一个能立即执行的验收方式（命令/测试/只能在本工作区里量的数字）。\n"
        "每种语言 3 件事，每件事 ≤30 个中文字符 / 16 个英文词左右。\n"
        "只返回 JSON：{\"zh\": [\"…\" | \"\"], \"en\": [\"…\"]}\n\n"
        f"快照：{body}"
    )


def _parse_plan(text: str):
    from .oracle_common import parse_json_object

    parsed = parse_json_object(text)
    if isinstance(parsed, dict):
        zh = parsed.get("zh") or []
        en = parsed.get("en") or []
        def _lines(value):
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()]
            return [str(value).strip()] if str(value).strip() else []
        return {"zh": _lines(zh), "en": _lines(en)}
    # non-JSON fallback — hand back the raw text as a single item per language
    lines = [seg.strip() for seg in text.splitlines() if seg.strip()]
    zh = [l for l in lines if any("一" in l or "二" in l or "三" in l or "中" in l for l in [l])][:3]
    return {"zh": zh or [text], "en": [text]}


def build_workspace_plan(*, config: Any | None = None, workspace: Path | None = None,
                         force_refresh: bool = False) -> dict[str, Any]:
    """Return the model-written plan; memoized unless force_refresh."""
    if not force_refresh:
        cached = memo_read(_CACHE_KEY)
        if isinstance(cached, dict) and cached.get("live") is not None:
            return cached

    root = Path(workspace) if workspace is not None else Path.cwd()
    if config is None:
        try:
            config = load_config(workspace=root)
        except Exception as exc:  # noqa: BLE001 - surface the outage, never 500
            return error_payload("config-unavailable", exc, lists=True)

    try:
        snapshot = _snapshot(root)
    except Exception as exc:  # noqa: BLE001 - a partial snapshot is reported, not raised
        return error_payload("snapshot-unavailable", exc, lists=True)

    try:
        call = call_model(config=config, prompt=_prompt(snapshot), max_tokens=420, temperature=0.25)
        plan = _parse_plan(call["text"])
        payload = {
            "live": True,
            "zh": plan["zh"],
            "en": plan["en"],
            "model": call["model"],
            "usage": call["usage"],
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        memo_write(_CACHE_KEY, payload)
        return payload
    except Exception as exc:  # noqa: BLE001 - the panel shows the outage, honestly
        return error_payload("model-unavailable", exc, lists=True)
