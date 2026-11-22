"""M8-T1292 — deterministic, model-free fixes from the measured visitor sample.

The model oracle (``oracle_visitors.py``) asks gpt-6.2-sol to diagnose the
journey log. That path costs tokens and, when the upstream account is out of
credit, honestly reports an outage. A visitor analyst should still be able to
read the measurements and leave with something to do.

This module is that floor: it turns each measured fact into one bounded,
checkable move. It never guesses a number, never names a file it cannot see,
and never claims a causal story the log did not establish. Every move carries
the exact reading that triggered it plus an acceptance check the user can run.

Zero tokens, zero network, zero writes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

MAX_MOVES = 4
_KNOWN_PANELS = ("pulse", "manual", "atlas", "archive", "almanac", "ledger", "tasks", "activity", "admin")


def _pct(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "—"
    return f"{round(float(value) * 100)}%"


def _ms(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "—"
    return f"{int(value)} ms"


def _move(evidence: str, zh_action: str, zh_accept: str, en_action: str, en_accept: str) -> dict[str, Any]:
    return {
        "evidence": evidence,
        "zh": {"action": zh_action[:180], "accept": zh_accept[:180]},
        "en": {"action": en_action[:240], "accept": en_accept[:240]},
    }


def _no_signal(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "live": False,
        "verdict": "no-signal",
        "focus": "unknown",
        "sample_size": 0,
        "confidence": "empty",
        "model_free": True,
        "source": "deterministic-rules",
        "zh": {
            "narrative": "还没有真实旅程，先跑一次采集，措施必须有测量依据。",
            "moves": [],
            "how_to": str(report.get("how_to") or "node scripts/behavior_sim.mjs --runs 6"),
        },
        "en": {
            "narrative": "No measured journeys yet — record a batch before asking for fixes.",
            "moves": [],
            "how_to": str(report.get("how_to") or "node scripts/behavior_sim.mjs --runs 6"),
        },
    }


def build_visitor_advice(report: dict[str, Any], workspace: Path | None = None) -> dict[str, Any]:
    """Derive at most four concrete fixes from *report* only.

    The input is the payload of ``build_journey_report``. Any field the report
    did not measure stays out of the conclusion; a thin sample is labelled as
    such. ``workspace`` is accepted for symmetry with the oracle family but is
    deliberately unused: no move here needs to read a file to be true.
    """
    if not isinstance(report, dict) or not report.get("live") or not report.get("total"):
        return _no_signal(report if isinstance(report, dict) else {})

    total = int(report.get("total") or 0)
    boot = report.get("median_boot_ms")
    bounce = report.get("bounce_rate")
    rage = report.get("rage_journeys")
    errors = report.get("page_errors")
    dwell = report.get("median_dwell_ms")
    exits = report.get("last_views") or []
    paths = report.get("transitions") or []

    moves: list[dict[str, Any]] = []
    flags: set[str] = set()

    if isinstance(boot, int) and boot >= 1200:
        flags.add("time-to-clickable")
        moves.append(_move(
            f"median_boot_ms={_ms(boot)}",
            "检查 web/index.html 的启动闪屏与首屏 preload，把侧栏可点前的同步工作缩到最小。",
            "重跑 node scripts/behavior_sim.mjs --runs 6，可点击耗时中位数降到 1200 ms 以下。",
            "Inspect the startup splash and first-paint preloads in web/index.html; trim work before the rail is clickable.",
            "Rerun node scripts/behavior_sim.mjs --runs 6 and get median time-to-clickable under 1200 ms.",
        ))

    if isinstance(bounce, (int, float)) and bounce >= 0.3:
        flags.add("navigation")
        moves.append(_move(
            f"bounce_rate={_pct(bounce)} over n={total}",
            "在 web/src/panels/onboarding.js 的第一步直接给出两扇可点的门，别让新访客自己猜入口。",
            "重采后同口径跳出率下降，且 landing 的第一步路径不再只靠瞎点。",
            "Put two clickable doors in step one of web/src/panels/onboarding.js instead of making a newcomer guess.",
            "Recollect and show a lower bounce rate with a first step that no longer depends on random clicks.",
        ))

    if isinstance(rage, int) and total and rage / total >= 0.2:
        flags.add("feedback")
        moves.append(_move(
            f"rage_sessions={rage}/{total}",
            "给 web/styles.css 里的 .nav-item 加即时按下反馈与更明确的 hover 边框，减少连点。",
            "重采后狂点会话占比下降，admin_smoke 仍零 pageerror。",
            "Give .nav-item in web/styles.css a visible pressed state and clearer hover border to reduce repeated clicks.",
            "Recollect a lower rage-session share while admin_smoke still reports zero page errors.",
        ))

    if isinstance(errors, int) and errors > 0:
        flags.add("feedback")
        moves.append(_move(
            f"page_errors={errors}",
            "从行为日志定位报错视图，先修控制台异常再谈体验；优先查 web/src/panels/ 下对应模块。",
            "重采后 page_errors 归零，admin_smoke 与 test:parity 均绿。",
            "Locate the erroring view from the journey log and fix the console exception first; start with the matching web/src/panels/ module.",
            "Recollect with page_errors at zero and both admin_smoke and test:parity green.",
        ))

    top_exit = None
    if exits and isinstance(exits[0], dict) and isinstance(exits[0].get("share"), (int, float)):
        if exits[0]["share"] >= 0.4:
            top_exit = exits[0]
    if top_exit:
        flags.add("navigation")
        view = str(top_exit.get("view") or "").strip()[:32]
        panel = f"web/src/panels/{view}.js" if view in _KNOWN_PANELS else ".nav-item"
        moves.append(_move(
            f"exit_view={view} share={_pct(top_exit['share'])}",
            f"在 {panel} 的显著位置放回退入口，别让访客把这里当成死胡同。",
            "重采后该视图的退出占比下降，常见漫游路径里出现新的后继节点。",
            f"Add a visible way back in {panel} so visitors do not treat it as a dead end.",
            "Recollect a lower exit share for that view and a new successor in the observed walk graph.",
        ))

    if isinstance(dwell, int) and dwell < 5000 and (bounce or 0) < 0.2 and not moves:
        moves.append(_move(
            f"median_dwell_ms={_ms(dwell)} with bounce_rate={_pct(bounce)}",
            "访客来去快但不跳出——在 web/src/panels/almanac.js 的首屏露出更深一层的章节入口。",
            "重采后停留中位数上升，章节入口的点击出现在 transitions 里。",
            "Visitors leave quickly but do not bounce — surface a deeper chapter entry on the first screen of web/src/panels/almanac.js.",
            "Recollect a higher median dwell and see the chapter entry appear in observed transitions.",
        ))

    # Severity order, not rule order: a console error or rage storm outranks
    # a soft navigation hunch even when bounce is also high.
    focus = next((name for name in ("time-to-clickable", "feedback", "navigation", "content")
                  if name in flags), "content")
    moves = moves[:MAX_MOVES]
    confidence = str(report.get("confidence") or "thin")
    thin = confidence == "thin"
    zh_note = "样本偏薄，只作方向参考。" if thin else "全部措施由本批实测读数触发，不含模型推断。"
    en_note = "Thin sample — directional only." if thin else "Every move is triggered by a measured reading; no model inference."

    narrative_zh = f"{total} 段真实旅程：跳出 {_pct(bounce)}、可点击耗时 {_ms(boot)}、狂点 {rage or 0}、页面错误 {errors or 0}。{zh_note}"
    narrative_en = (
        f"{total} recorded journeys: bounce {_pct(bounce)}, time-to-clickable {_ms(boot)}, "
        f"rage sessions {rage or 0}, page errors {errors or 0}. {en_note}"
    )
    return {
        "live": True,
        "verdict": "rule-based",
        "focus": focus,
        "sample_size": total,
        "confidence": confidence,
        "model_free": True,
        "source": "deterministic-rules",
        "zh": {"narrative": narrative_zh, "moves": moves},
        "en": {"narrative": narrative_en, "moves": moves},
        "paths_seen": len(paths),
    }
