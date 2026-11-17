"""Live recommendations — the model reads the same snapshot and tells this workspace three moves.

The rule-based ``recommendations`` in minicc/admin.py catalog *known shapes* (restart-attached
interruptions, weekend-fading, low cache rate). That is valuable but shallow. The model adds what
no rule encodes: it weighs the whole measured picture at once — trend, peak, streak, tool
usage, interrupt causes — and writes three specificity-checked recommendations, each with one
concrete acceptance check (a command, a test, or a number that can only be measured in this
workspace). Always grounded; never motivational filler.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .admin import build_summary
from .config import load_config
from .oracle_common import call_model, error_payload, memo_read, memo_write
from .stats import gather

_CACHE_KEY = "oracle-recommendations:v1"


def _snapshot(workspace: Path) -> dict[str, Any]:
    stats = gather(workspace)
    summary = build_summary(workspace)
    totals = summary.get("totals") or {}
    trend = summary.get("trend_7d") or []
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
        "trend_7d": trend,
        "rule_based_recommendations": summary.get("recommendations") or [],
    }


def _prompt(snapshot: dict[str, Any]) -> str:
    body = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    return (
        "你是本地优先编程工作台 minicc 的值守军师。下面是它自己的实测数据：\n\n"
        f"{body}\n\n"
        "任务：用这个快照为这台工作区写三条下一步最值得做的深度优化项，按优先级排列（第一条最值得的）。\n"
        "纪律：\n"
        "1) 只能引用“这个 JSON 里被证明过”的数字 / 名称 / 日期；引用 JSON 里没有的东西就是造假，禁止。\n"
        "2) 每条都要有（i）一句具体到文件/命令/数字的行动，（ii）一个用户能马上验证的验收标准（命令/测试/只能量一次的数字）。\n"
        "3) “优化、提升、重构、策略”这类无文无锚的词一律禁用；英文是 optimize、improve、refactor、strategy。\n"
        "4) 与 rule_based_recommendations 里已给的三条形状不互相复述——能讲新的就讲新的；不能就靠明言为什么做了保护。\n"
        "5) 每句中文 ≤ 45 字符、每条英文 ≤ 24 词。\n"
        "只返回 JSON：{\"zh\": [\"…\"], \"en\": [\"…\"]}"
    )


def build_workspace_recommendations(*, config: Any | None = None, workspace: Path | None = None,
                                     force_refresh: bool = False) -> dict[str, Any]:
    """Return the model-written recommendations; memoized (10 min) unless forced."""
    if not force_refresh:
        cached = memo_read(_CACHE_KEY)
        if isinstance(cached, dict) and cached.get("live") is not None:
            return cached

    root = Path(workspace) if workspace is not None else Path.cwd()
    try:
        snapshot = _snapshot(root)
    except Exception as exc:  # noqa: BLE001 - a partial snapshot is reported, never raised
        return error_payload("snapshot-unavailable", exc, lists=True)

    # Zero signal: no tasks, no cache measurement, nothing in trend — no model call.
    totals_empty = (snapshot.get("tasks_total") in (0, None)
                    and snapshot.get("llm_cache_rate") is None
                    and all(float((entry or {}).get("events", 0) or 0) == 0
                            for entry in snapshot.get("trend_7d") or []))
    if totals_empty:
        payload = {
            "live": True,
            "verdict": "no-signal",
            "zh": ["这台工作区没有可分析的操作信号——任务、缓存、审计七天事件都是零。唯一诚实的建议：先跑一次真实任务。"],
            "en": ["This workspace carries no operational signal yet — zero tasks, no cache measurement, zero events over seven days. The only honest move: run a real task first."],
        }
        memo_write(_CACHE_KEY, payload)
        return payload

    if config is None:
        try:
            config = load_config(workspace=root)
        except Exception as exc:  # noqa: BLE001 - surface the outage, never 500
            return error_payload("config-unavailable", exc, lists=True)

    try:
        call = call_model(config=config, prompt=_prompt(snapshot), max_tokens=500, temperature=0.25)
        from .oracle_common import parse_json_object

        parsed = parse_json_object(call["text"])

        def _lines(value):
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()][:6]
            return [str(value).strip()] if str(value).strip() else []

        zh = _lines(parsed.get("zh")) if isinstance(parsed, dict) else []
        en = _lines(parsed.get("en")) if isinstance(parsed, dict) else []
        payload = {
            "live": True,
            "verdict": "model-recommendations",
            "zh": zh,
            "en": en,
            "model": call["model"],
            "usage": call["usage"],
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        memo_write(_CACHE_KEY, payload)
        return payload
    except Exception as exc:  # noqa: BLE001 - the panel shows the outage, honestly
        return error_payload("model-unavailable", exc, lists=True)
