"""The model, on duty, reads this repository's own audit trail and tells it back in words.

Every line in ``.minicc/audit.jsonl`` is a real keystroke the agent made against this
tree — a read, a write, a stage, a commit — with a digest pair.  The model is given the
last slice of those lines verbatim and asked to answer three questions:

1. What actually happened in this window (read the actions, not the words);
2. What does a careful operator notice — a file churned, a rule that appeared, a phase
   that flipped, a denied path that kept showing up;
3. What the next person should look at first.

Honesty contract (same as every oracle tile):

- no audit / no records → ``no-audit`` verdict, no model call;
- the wire keeps only real digest lines; the model never sees anything else, and if it
  answers nothing the panel says so instead of inventing;
- the model is told to describe THIS window and no other — inventing dates, figures,
  or consequences outside the slice is the one mistake the prompt forbids outright.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .oracle_common import call_model, cached_zh_en, error_payload, memo_read, memo_write

_CACHE_KEY = "oracle-audit-story:v1"
_SLICE_LINES = 64
_SLICE_BYTES = 24000


def _slice(workspace: Path) -> dict[str, Any] | None:
    path = workspace / ".minicc" / "audit.jsonl"
    if not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if not lines:
        return None
    lines = [line for line in lines if line.strip()]
    if not lines:
        return None
    window = lines[-_SLICE_LINES:]
    digest = []
    for line in window:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            digest.append({"action": "unparsable", "path": None, "detail": line[:120]})
            continue
        entry = {
            "action": obj.get("action"),
            "path": obj.get("path"),
            "detail": str(obj.get("detail", ""))[:120],
            "when": str(obj.get("timestamp", ""))[:19],
        }
        digest.append(entry)
    return {
        "total_lines": len(lines),
        "window_size": len(window),
        "window_from": (digest[0].get("when") if digest else ""),
        "window_to": (digest[-1].get("when") if digest else ""),
        "entries": digest,
    }


def _prompt(snapshot: dict[str, Any]) -> str:
    blob = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))[:_SLICE_BYTES]
    return (
        "你是 minicc 仓库的审计员。下面是 .minicc/audit.jsonl 里最近窗口的原始条目（真实记录，不是演示数据）：\n\n"
        f"{blob}\n\n"
        "请读这一段记录，写三段（中文 ≤ 3 句、英文 ≤ 3 句）：\n"
        "① 这段窗口里真正发生了什么（按 action 与 path 的出现频率回答，不虚构文件名）；\n"
        "② 一个值得留意的反常或重复（哪个 path 被反复写过、哪类动作出现了、哪次读取像是确认性重读——只基于给定行）；\n"
        "③ 下一步应该先看哪一处（一个具体 path 或一个具体动作，不要空话）。\n\n"
        "纪律：只引用上面 JSON 里出现过的 path 与 action；不推测原因，不给时间之外的叙事；"
        "没有反常可报就直说“data does not show one”。\n"
        "只返回 JSON：{\"zh\": \"…\", \"en\": \"…\"}"
    )


def build_audit_story(*, config: Any | None = None, workspace: Path | None = None,
                      force_refresh: bool = False) -> dict[str, Any]:
    """Return the model's bilingual reading of the last slice of audit records, memoized."""
    if not force_refresh:
        cached = memo_read(_CACHE_KEY)
        if isinstance(cached, dict) and cached.get("live") is not None:
            return cached

    root = Path(workspace) if workspace is not None else Path.cwd()
    snapshot = _slice(root)
    if snapshot is None:
        payload = {
            "live": True,
            "verdict": "no-audit",
            "zh": "这一窗口里没有审计记录可读——没有改动就没有故事，这是唯一诚实的句子。",
            "en": "No audit trail to read in this window. With nothing changed, there is no story; that is the honest sentence.",
        }
        memo_write(_CACHE_KEY, payload)
        return payload

    if config is None:
        try:
            from .config import load_config

            config = load_config(workspace=root)
        except Exception as exc:  # noqa: BLE001 - surface the outage, never 500
            return error_payload("config-unavailable", exc)

    try:
        call = call_model(config=config, prompt=_prompt(snapshot), max_tokens=480, temperature=0.2)
        story = cached_zh_en(call["text"])
        payload = {
            "live": True,
            "verdict": "model-story",
            "zh": story["zh"],
            "en": story["en"],
            "model": call["model"],
            "usage": call["usage"],
            "total_lines": snapshot["total_lines"],
            "window_size": snapshot["window_size"],
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        memo_write(_CACHE_KEY, payload)
        return payload
    except Exception as exc:  # noqa: BLE001 - the panel shows the outage, honestly
        return error_payload("model-unavailable", exc)
