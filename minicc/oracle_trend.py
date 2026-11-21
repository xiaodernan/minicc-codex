"""Live trend analyst — the model reads this workspace's real seven-day series.

The admin panel already draws a 7-day event bar chart and a deliberately naive
linear ``forecast`` (minicc.admin._forecast_from_trend). That projection is honest
but shallow: a straight line cannot weigh the peak, the streak, interrupt causes
or the cache reading together, nor can it write a next move a human can verify.

This oracle hands the model the *same measured series plus the rule baseline* and
asks for three things a rule cannot do: a trend reading grounded in the real
readings, a direction verdict cross-checked against the linear baseline, and up
to four deep next moves — each with a concrete, in-workspace acceptance check.

Discipline shared with the rest of the oracle family (see ``oracle_common.py``):
zero signal costs zero tokens; an unreachable model is reported live:false and
never raises; a second call rides the memo; the prompt carries measured data only.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .admin import build_summary
from .config import load_config
from .oracle_common import call_model, memo_read, memo_write, parse_json_object
from .stats import gather

_CACHE_KEY = "oracle-trend:v1"
_DIRECTIONS = ("cooling", "rising", "steady")


def _snapshot(workspace: Path, *, stats: Any = None, summary: Any = None) -> dict[str, Any]:
    stats = stats if stats is not None else gather(workspace)
    summary = summary if summary is not None else build_summary(workspace)
    totals = summary.get("totals") or {}
    return {
        "trend_7d": summary.get("trend_7d") or [],
        "forecast": summary.get("forecast"),
        "tasks_total": totals.get("tasks"),
        "tasks_completed": totals.get("completed"),
        "tasks_interrupted": totals.get("interrupted"),
        "cache_hit_rate": totals.get("cache_hit_rate"),
        "llm_cache_rate": (stats.get("llm_cache") or {}).get("hit_rate"),
        "audit_lines": totals.get("audit_lines"),
        "sessions": totals.get("sessions"),
        "completion_streak": summary.get("completion_streak"),
        "interrupt_causes": summary.get("interrupt_causes"),
        "top_tools": (summary.get("tool_usage") or [])[:5],
        "rule_recommendations": summary.get("recommendations") or [],
    }


def _prompt(snapshot: dict[str, Any]) -> str:
    body = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    return (
        "你是本地优先编程工作台 minicc 的值守趋势研判官。下面 JSON 是它七天真实事件序列、"
        "一条刻意朴素的线性回归基线（forecast），以及同一次快照里的实测计数。\n"
        "任务：\n"
        "1) narrative：一句话判读这条趋势，必须把序列里真实存在的读数（峰值日/近两日均值/斜率/"
        "中断原因之一）写进句子，不许编造 JSON 里没有的数字。\n"
        "2) direction：只能是 cooling、rising、steady 三者之一；若你的判断与 forecast.direction "
        "不同，在 narrative 里说明为什么这条序列让你 disagree。\n"
        "3) moves：至多四条下一步深度优化措施，每条必须同时含（i）具体到文件/命令/数字的动作，"
        "（ii）用户能立刻验证的验收标准；不得与 rule_recommendations 复述；"
        "“优化/提升/重构/策略”这类空词一律禁用（英文 optimize/improve/refactor/strategy）。\n"
        "纪律：中文 narrative ≤ 45 字、每条 move ≤ 45 字；英文 narrative ≤ 24 词、每条 move ≤ 24 词。\n"
        "只返回 JSON，不要额外正文：\n"
        '{"direction":"cooling|rising|steady","zh":{"narrative":"…","moves":["…"]},'
        '"en":{"narrative":"…","moves":["…"]}}\n\n'
        f"实测快照：{body}"
    )


def _bilingual(value: Any) -> dict[str, Any]:
    """Coerce a possibly-malformed model value into a stable panel shape."""
    if not isinstance(value, dict):
        return {"narrative": "", "moves": []}
    narrative = str(value.get("narrative") or "").strip()[:320]
    raw = value.get("moves")
    moves: list[str] = []
    if isinstance(raw, list):
        moves = [str(item).strip()[:160] for item in raw if str(item).strip()]
    elif isinstance(raw, str) and raw.strip():
        moves = [raw.strip()[:160]]
    return {"narrative": narrative, "moves": moves[:4]}


def _no_signal_payload() -> dict[str, Any]:
    return {
        "live": True,
        "verdict": "no-signal",
        "direction": "unknown",
        "baseline_direction": None,
        "zh": {"narrative": "这台工作区七天里没有事件、没有任务、也没有缓存读数——趋势无可研判。先跑一次真实任务。",
               "moves": []},
        "en": {"narrative": "No events, tasks or cache reading across seven days — there is no trend to read. Run one real task first.",
               "moves": []},
    }


def _outage_payload(kind: str, exc: Exception) -> dict[str, Any]:
    """Same shape as a live verdict so the panel never has to branch on keys."""
    empty = {"narrative": "", "moves": []}
    return {
        "live": False,
        "verdict": kind,
        "direction": "unknown",
        "baseline_direction": None,
        "zh": dict(empty),
        "en": dict(empty),
        "error": f"{type(exc).__name__}: {exc}",
    }


def build_trend_insight(*, config: Any | None = None, workspace: Path | None = None,
                        stats: Any = None, summary: Any = None,
                        force_refresh: bool = False) -> dict[str, Any]:
    """Return the model-written trend reading; memoized (10 min) unless forced.

    ``stats`` / ``summary`` accept the service-layer memoized values so the
    oracle does not walk the whole workspace a second time per call.
    """
    if not force_refresh:
        cached = memo_read(_CACHE_KEY)
        if isinstance(cached, dict) and cached.get("live") is not None:
            return cached

    root = Path(workspace) if workspace is not None else Path.cwd()
    try:
        snapshot = _snapshot(root, stats=stats, summary=summary)
    except Exception as exc:  # noqa: BLE001 - a partial snapshot is reported, never raised
        return _outage_payload("snapshot-unavailable", exc)

    totals_empty = (snapshot.get("tasks_total") in (0, None)
                    and snapshot.get("llm_cache_rate") is None
                    and all(float((entry or {}).get("events", 0) or 0) == 0
                            for entry in snapshot.get("trend_7d") or []))
    if totals_empty:
        payload = _no_signal_payload()
        memo_write(_CACHE_KEY, payload)
        return payload

    if config is None:
        try:
            config = load_config(workspace=root)
        except Exception as exc:  # noqa: BLE001 - surface the outage, never 500
            return _outage_payload("config-unavailable", exc)

    try:
        call = call_model(config=config, prompt=_prompt(snapshot), max_tokens=640, temperature=0.25)
        parsed = parse_json_object(call["text"])
        if not isinstance(parsed, dict) or not (str(parsed.get("zh") or "") or str(parsed.get("en") or "")):
            # A non-JSON answer is not a verdict — fail closed, never paint a blank panel green.
            return _outage_payload("unparsable-model-answer", ValueError("model did not return a zh/en JSON object"))
        direction = str(parsed.get("direction") or "").strip().lower()
        if direction not in _DIRECTIONS:
            direction = "unknown"
        forecast = snapshot.get("forecast") or {}
        payload = {
            "live": True,
            "verdict": "model-trend",
            "direction": direction,
            "baseline_direction": forecast.get("direction") if isinstance(forecast, dict) else None,
            "zh": _bilingual(parsed.get("zh") if isinstance(parsed, dict) else None),
            "en": _bilingual(parsed.get("en") if isinstance(parsed, dict) else None),
            "model": call["model"],
            "usage": call["usage"],
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        memo_write(_CACHE_KEY, payload)
        return payload
    except Exception as exc:  # noqa: BLE001 - the panel shows the outage, honestly
        return _outage_payload("model-unavailable", exc)
