"""Live workspace brief — the model on duty for this workspace.

A deep, on-demand integration: the configured model reads the *measured*
fact pack of this workspace (git-derived digest, task store summary, 7-day
events trend) and writes a two-part (zh + en) brief for whoever just opened
the admin panel. The model sees no secrets — only the counters and dates a
visitor of the panel may already read — and answers with a hard JSON
contract so the panel never paints an unparsable page.

Discipline matched to the rest of the product:

* same provider settings as every other live call (MINICC_* env), never
  printing the key;
* a stable prompt_cache_key — one prefix, identical bytes, measurable hits
  (measured_usage carries cached_tokens when the gateway reports it; the
  absence is reported, never fabricated);
* 10-minute memo per process so an unlock burst does not re-burn tokens;
  ``force_refresh=True`` bypasses the memo;
* every failure path returns an honest payload with ``live: False`` — the
  panel shows the outage instead of a story.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from .admin import build_summary
from .config import load_config
from .digest import build_digest
from .llm.usage import token_count
from .redis_cache import default_cache
from .stats import gather

_TTL_SECONDS = 600
_CACHE_KEY = "oracle-brief:v1"
_USER_AGENT = "minicc-oracle"


def _prompt_cache_key(base_url: str, model: str, explicit: str = "") -> str:
    explicit = (explicit or "").strip()[:64]
    if explicit:
        return explicit
    return f"minicc-{hashlib.sha256(f'{base_url}|{model}'.encode('utf-8')).hexdigest()[:16]}"


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


def _parse_brief(text: str) -> dict[str, str]:
    text = text.strip()
    if text.startswith("```"):
        # tolerate a fenced block without pretending it was clean JSON
        inner = text.split("\n", 1)[-1]
        text = inner.rsplit("```", 1)[0].strip()
    try:
        parsed = json.loads(text)
    except ValueError:
        return {"zh": text, "en": text} if text else {"zh": "", "en": ""}
    if not isinstance(parsed, dict):
        return {"zh": text, "en": text}
    zh = str(parsed.get("zh") or "").strip()
    en = str(parsed.get("en") or "").strip()
    return {"zh": zh, "en": en or zh}


def _error_payload(kind: str, exc: Exception) -> dict[str, Any]:
    return {
        "live": False,
        "zh": "",
        "en": "",
        "model": None,
        "usage": None,
        "error": f"{kind}: {type(exc).__name__}: {exc}",
    }


def build_workspace_brief(*, config: Any | None = None, workspace: Path | None = None,
                          force_refresh: bool = False) -> dict[str, Any]:
    """Return the model-written workspace brief; memoized unless force_refresh."""
    if not force_refresh:
        try:
            cached = default_cache.get(_CACHE_KEY)
        except Exception:  # noqa: BLE001 - a cache read failure falls through to a fresh brief
            cached = None
        if isinstance(cached, dict) and cached.get("live") is not None:
            return cached

    root = Path(workspace) if workspace is not None else Path.cwd()
    if config is None:
        try:
            config = load_config(workspace=root)
        except Exception as exc:  # noqa: BLE001 - surface the outage, never 500
            return _error_payload("config-unavailable", exc)

    try:
        snapshot = _snapshot(root)
    except Exception as exc:  # noqa: BLE001 - a partial snapshot is reported, not raised
        return _error_payload("snapshot-unavailable", exc)

    try:
        from openai import OpenAI

        model_name = str(getattr(config, "model", "") or "")
        base_url = str(getattr(config, "base_url", "") or "")
        api_key = str(getattr(config, "api_key", "") or "")
        explicit_key = str(getattr(config, "prompt_cache_key", "") or "")
        cache_key = _prompt_cache_key(base_url, model_name, explicit_key)

        client = OpenAI(api_key=api_key, base_url=base_url, timeout=60, max_retries=0)
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": _prompt(snapshot)}],
            max_tokens=280,
            temperature=0.2,
            prompt_cache_key=cache_key,
        )
        text = (response.choices[0].message.content or "").strip()
        brief = _parse_brief(text)
        usage_obj = getattr(response, "usage", None)
        usage = {
            "prompt_tokens": token_count(getattr(usage_obj, "prompt_tokens", 0), 0) or 0,
            "completion_tokens": token_count(getattr(usage_obj, "completion_tokens", 0), 0) or 0,
            "total_tokens": token_count(getattr(usage_obj, "total_tokens", None), None),
        }
        details = getattr(usage_obj, "prompt_tokens_details", None)
        cached_tokens = getattr(details, "cached_tokens", None) if details is not None else None
        if cached_tokens is not None:
            usage["cached_tokens"] = token_count(cached_tokens, 0) or 0
        payload = {
            "live": True,
            "zh": brief["zh"],
            "en": brief["en"],
            "model": model_name,
            "usage": usage,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        try:
            default_cache.set(_CACHE_KEY, payload, ttl=_TTL_SECONDS)
        except Exception:  # noqa: BLE001 - memo write failure never breaks the answer
            pass
        return payload
    except Exception as exc:  # noqa: BLE001 - the panel shows the outage, honestly
        return _error_payload("model-unavailable", exc)
