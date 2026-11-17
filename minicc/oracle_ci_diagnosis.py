"""The model triages this repository's mainline red — reading only the wire, never inventing.

This is the one state-flow in the product where "an LLM looked at the failure
and told a human what to check first" is unambiguously better than an alert
badge.  The data source is the same GitHub REST wire the admin CI tile shows
(:mod:`minicc.ci_health`) — no logs are streamed, no blame is assigned, and
the model is told, in the prompt, that it may only point at failure families
this repository has actually produced, or say it cannot tell.

Honesty contract:

- wire unreachable → ``live=False`` + reason, model NOT called;
- latest mainline run green → ``live=True, verdict="no-current-failure"`` and the
  model is NOT called (no token is spent on a green repo — and the payload says so);
- latest run is a failure → the model attributes the failure and names ONE safest
  next step.  The answer is labelled analysis, never proof, and it never names
  a file, line, or fix that is not present in the wire JSON.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .oracle_common import call_model, cached_zh_en, error_payload, memo_read, memo_write
from .ci_health import fetch_ci_health

_CACHE_KEY = "oracle-ci-diagnosis:v2"

_FAILURE_FAMILIES_ZH = (
    "① 双语化搬迁时 docstring 引文没重新瞄准；"
    "② one-home 钉死的内联字面量在消息表里被换了位置；"
    "③ 围栏尺子函数改名/名册宽面少登记；"
    "④ CRLF/换行端点变了；"
    "⑤ subprocess.run 超时没 catch TimeoutExpired；"
    "⑥ 冒烟测试 60 秒白等一个 2 分钟以上的后台检查"
)


def _snapshot() -> dict[str, Any]:
    health = fetch_ci_health()
    return {
        "live": bool(health.get("live")),
        "latest": health.get("latest_run") or {},
        "recent": health.get("recent") or [],
        "generated_at": health.get("generated_at"),
    }


def _prompt(snapshot: dict[str, Any]) -> str:
    blob = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    return (
        "你是 minicc 仓库的值班守门人。下面是来自 GitHub REST 的 main 分支真实数据（最近三条运行）：\n\n"
        f"{blob}\n\n"
        "请对这个红灯写一份**归因与下一步**（中文 ≤ 3 句、英文 ≤ 3 句）：\n"
        "① 哪条 workflow 在哪个 commit 红了；\n"
        "② 在下面这六类红里最可能是哪一类（只指，不许断言 —— 没有把握就说“无法从这六类里判定”）：\n"
        f"{_FAILURE_FAMILIES_ZH}；\n"
        "③ 下一步最安全的动作（只给一条，不写修复 diff）。\n\n"
        "纪律：只引用上面 JSON 里的事实；没红的运行不归因；"
        "不要说任何 JSON 里不存在的 commit sha 或 workflow 名。\n"
        "只返回 JSON：{\"zh\": \"…\", \"en\": \"…\"}"
    )


def build_ci_diagnosis(*, config: Any | None = None, workspace: Path | None = None,
                       force_refresh: bool = False) -> dict[str, Any]:
    """Return the model's attribution for the latest mainline red, or an honest no-op."""
    if not force_refresh:
        cached = memo_read(_CACHE_KEY)
        if isinstance(cached, dict) and cached.get("live") is not None:
            return cached

    snapshot = _snapshot()
    if not snapshot["live"]:
        return {
            "live": False,
            "error": "github-wire-unavailable: 最近 3 条主线运行拿不到（GitHub REST 未应答或无权限）",
            "verdict": "wire-down",
        }

    latest = snapshot["latest"]
    status = str(latest.get("status") or "")
    conclusion = str(latest.get("conclusion") or "")
    if status and status != "completed":
        # The wire's conclusion is not in yet — attributing a red that has not
        # materialized would spend tokens on fiction. The panel shows the status honestly.
        payload = {
            "live": True,
            "verdict": "pending",
            "zh": f"最新一次 CI（{latest.get('head_sha') or '?'}）还在排队或运行中——结论出来之前不归因；浪费 token 去诊断一个还没发生的红没有意义，结论落地后按下刷新即可。",
            "en": f"The latest CI run ({latest.get('head_sha') or '?'}) is queued or in flight. Diagnosing a red that has not happened would spend tokens on fiction; press refresh once it concludes.",
            "head_sha": latest.get("head_sha"),
            "workflow": latest.get("workflow"),
            "status": status,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        memo_write(_CACHE_KEY, payload)
        return payload
    if conclusion != "failure":
        payload = {
            "live": True,
            "verdict": "no-current-failure",
            "zh": "当前 main 没有处于失败状态（或失败已经落在最近三条窗口之外）。本次没有调用模型，也没有产生 token 成本。",
            "en": "main is not failing right now (or the failure fell out of the last-three window). No model was called; zero tokens were spent.",
            "head_sha": latest.get("head_sha"),
            "workflow": latest.get("workflow"),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        memo_write(_CACHE_KEY, payload)
        return payload

    if config is None:
        try:
            from .config import load_config

            config = load_config(workspace=Path(workspace) if workspace is not None else Path.cwd())
        except Exception as exc:  # noqa: BLE001 - surface the outage, never 500
            return error_payload("config-unavailable", exc)

    try:
        call = call_model(config=config, prompt=_prompt(snapshot), max_tokens=420, temperature=0.15)
        diagnosis = cached_zh_en(call["text"])
        payload = {
            "live": True,
            "verdict": "model-diagnosis",
            "zh": diagnosis["zh"],
            "en": diagnosis["en"],
            "model": call["model"],
            "usage": call["usage"],
            "head_sha": latest.get("head_sha"),
            "workflow": latest.get("workflow"),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        memo_write(_CACHE_KEY, payload)
        return payload
    except Exception as exc:  # noqa: BLE001 - the panel shows the outage, honestly
        return error_payload("model-unavailable", exc)

