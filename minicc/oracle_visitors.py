"""M8-T1289b — the model reads the synthetic visitor log and names the top fix.

``minicc/behavior_journeys.py`` answers *what happened*: 15 sessions, a third of
them bounced, median dwell 7.9 s, three rage bursts, the rail became clickable
after 1.06 s. It deliberately stops there — counting is not diagnosis.

This oracle closes the loop the brief asks for: take that measured sample and
have the model name the single biggest obstacle plus up to four fixes, each with
an acceptance check the user can run. The model only ever sees numbers the
journey log produced; nothing here invents a session.

Discipline shared with the oracle family:

* an empty log costs zero tokens — there is nothing to read, and the payload
  says so in both languages;
* a model failure or an unparsable answer is ``live: False`` and never raises;
* the memo is keyed to the sample's own signature, so re-running the simulator
  invalidates the reading instead of serving yesterday's opinion;
* a ``focus`` outside the vocabulary fails closed to ``unknown``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .behavior_journeys import build_journey_report
from .config import load_config
from .oracle_common import call_model, memo_read, memo_write, parse_json_object

_CACHE_KEY = "oracle-visitors:v1"
_FOCUS = ("time-to-clickable", "navigation", "feedback", "content")
_KNOWN_VIEWS = ("pulse", "manual", "atlas", "archive", "almanac", "ledger", "tasks", "activity", "workspace")
_KNOWN_COMMANDS = (
    "npm run build:web",
    "npm run check:web",
    "node scripts/behavior_sim.mjs --runs 6",
    "python -m minicc.web --port 8765",
)


def _known_files(root: Path) -> list[str]:
    """The real files a fix may point at — read from disk, never guessed.

    Without this the model writes plausible paths that do not exist
    (``web/src/panels/landing.js`` was its first answer). Naming a file that is
    not here is a hallucination, so the prompt only lets it choose from this list.
    """
    files = ["web/index.html", "web/styles.css", "web/src/main.js", "web/src/core/i18n.js"]
    try:
        panels = sorted(path.name for path in (root / "web" / "src" / "panels").glob("*.js"))
    except OSError:
        panels = []
    return files + [f"web/src/panels/{name}" for name in panels[:24]]


def _signature(report: dict[str, Any]) -> str:
    window = report.get("window") or {}
    return f"{report.get('total')}:{window.get('end') or 'none'}"


def _snapshot(report: dict[str, Any], root: Path) -> dict[str, Any]:
    """The measured sample, trimmed to what a diagnosis actually needs."""
    return {
        "sample_size": report.get("total"),
        "confidence": report.get("confidence"),
        "bounce_rate": report.get("bounce_rate"),
        "median_dwell_ms": report.get("median_dwell_ms"),
        "median_boot_ms": report.get("median_boot_ms"),
        "rage_sessions": report.get("rage_journeys"),
        "page_errors": report.get("page_errors"),
        "personas": [
            {
                "id": row.get("id"),
                "runs": row.get("runs"),
                "bounce_rate": row.get("bounce_rate"),
                "median_dwell_ms": row.get("median_dwell_ms"),
                "mean_clicks": row.get("mean_clicks"),
                "top_exit": row.get("top_exit"),
            }
            for row in report.get("personas") or []
        ],
        "exit_views": [
            {"view": row.get("view"), "share": row.get("share")} for row in report.get("last_views") or []
        ],
        "known_views": list(_KNOWN_VIEWS),
        "known_files": _known_files(root),
        "known_commands": list(_KNOWN_COMMANDS),
    }


def _prompt(snapshot: dict[str, Any]) -> str:
    body = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    return (
        "你是本地优先编程工作台 minicc 的值守体验分析师。下面 JSON 是一批**真实无头浏览器**会话的聚合："
        "五种访客性格（impatient / wanderer / reader / explorer / power）真的打开了界面、真的点击、真的离开。"
        "数字全部来自这些会话，一个都没有编。\n"
        "任务：\n"
        "1) narrative：一句话判读这批访客卡在哪，必须引用 JSON 里真实存在的读数"
        "（bounce_rate / median_dwell_ms / median_boot_ms / rage_sessions / 某个 exit_views.view），"
        "不许出现 JSON 里没有的数字。\n"
        "2) focus：只能取 time-to-clickable、navigation、feedback、content 之一。"
        "median_boot_ms 明显偏高选第一个；跳出集中在某几个视图选 navigation；"
        "rage_sessions 占比高选 feedback；停留很短但也不跳出选 content。\n"
        "3) moves：至多四条具体修复，每条必须同时含（i）动作落到真实的文件、选择器或命令"
        "——文件路径**只能**取自 known_files，命令**只能**取自 known_commands，"
        "点不到具体文件时就写选择器（如 .nav-item）或视图名，绝不编一个不存在的路径"
        "（ii）用户当场能验证的验收标准；"
        "“优化/提升/重构/策略”这类空词一律禁用（英文 optimize/improve/refactor/strategy）。\n"
        "纪律：中文 narrative ≤ 45 字、每条 move ≤ 48 字；英文 narrative ≤ 24 词、每条 move ≤ 26 词。\n"
        "只返回 JSON，不要额外正文：\n"
        '{"focus":"time-to-clickable|navigation|feedback|content","zh":{"narrative":"…","moves":["…"]},'
        '"en":{"narrative":"…","moves":["…"]}}\n\n'
        f"实测样本：{body}"
    )


def _bilingual(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"narrative": "", "moves": []}
    narrative = str(value.get("narrative") or "").strip()[:320]
    raw = value.get("moves")
    moves: list[str] = []
    if isinstance(raw, list):
        moves = [str(item).strip()[:180] for item in raw if str(item).strip()]
    elif isinstance(raw, str) and raw.strip():
        moves = [raw.strip()[:180]]
    return {"narrative": narrative, "moves": moves[:4]}


def _no_signal_payload(signature: str) -> dict[str, Any]:
    return {
        "live": True,
        "verdict": "no-signal",
        "focus": "unknown",
        "signature": signature,
        "zh": {"narrative": "还没有真实旅程可读——先跑一次采集，日志里才会有访客。", "moves": []},
        "en": {"narrative": "No real journeys to read yet — record a batch first, then there is a visitor to diagnose.", "moves": []},
    }


def _outage_payload(kind: str, exc: Exception) -> dict[str, Any]:
    """Same shape as a live reading so the panel never branches on keys."""
    empty = {"narrative": "", "moves": []}
    return {
        "live": False,
        "verdict": kind,
        "focus": "unknown",
        "zh": dict(empty),
        "en": dict(empty),
        "error": f"{type(exc).__name__}: {exc}",
    }


def build_visitor_insight(*, config: Any | None = None, workspace: Path | None = None,
                          report: dict[str, Any] | None = None,
                          force_refresh: bool = False) -> dict[str, Any]:
    """Return the model-written reading of the visitor sample, memoized by sample.

    ``report`` accepts the service-layer value so the oracle does not read the
    journey log twice on one request.
    """
    root = Path(workspace) if workspace is not None else Path.cwd()
    try:
        report = report if isinstance(report, dict) else build_journey_report(root)
    except Exception as exc:  # noqa: BLE001 - a broken log is an honest outage, never a 500
        return _outage_payload("log-unavailable", exc)

    signature = _signature(report)
    if not force_refresh:
        cached = memo_read(_CACHE_KEY)
        if isinstance(cached, dict) and cached.get("live") is not None and cached.get("signature") == signature:
            return cached

    if not report.get("live"):
        payload = _no_signal_payload(signature)
        memo_write(_CACHE_KEY, payload)
        return payload

    if config is None:
        try:
            config = load_config(workspace=root)
        except Exception as exc:  # noqa: BLE001 - surface the outage, never 500
            return _outage_payload("config-unavailable", exc)

    try:
        call = call_model(config=config, prompt=_prompt(_snapshot(report, root)), max_tokens=700, temperature=0.3)
        parsed = parse_json_object(call["text"])
        if not isinstance(parsed, dict) or not (parsed.get("zh") or parsed.get("en")):
            return _outage_payload("unparsable-model-answer", ValueError("model did not return a zh/en JSON object"))
        focus = str(parsed.get("focus") or "").strip().lower()
        if focus not in _FOCUS:
            focus = "unknown"
        payload = {
            "live": True,
            "verdict": "model-visitors",
            "focus": focus,
            "signature": signature,
            "sample": {
                "total": report.get("total"),
                "bounce_rate": report.get("bounce_rate"),
                "median_dwell_ms": report.get("median_dwell_ms"),
                "median_boot_ms": report.get("median_boot_ms"),
                "confidence": report.get("confidence"),
            },
            "zh": _bilingual(parsed.get("zh")),
            "en": _bilingual(parsed.get("en")),
            "model": call["model"],
            "usage": call["usage"],
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        memo_write(_CACHE_KEY, payload)
        return payload
    except Exception as exc:  # noqa: BLE001 - the panel shows the outage, honestly
        return _outage_payload("model-unavailable", exc)
