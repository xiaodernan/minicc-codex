"""Usage normalization shared by providers, agent runs, and task snapshots."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from math import isfinite
from typing import Any


USAGE_TOKEN_KEYS = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "reasoning_tokens",
    "prompt_cache_hit_tokens",
    "prompt_cache_miss_tokens",
    "prompt_cache_write_tokens",
)
CACHE_TOKEN_KEYS = (
    "prompt_cache_hit_tokens",
    "prompt_cache_miss_tokens",
    "prompt_cache_write_tokens",
)


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and isfinite(value):
        return value
    return None


def cache_summary(usage: Mapping[str, Any] | None) -> dict[str, Any]:
    """Summarize cache counters without treating missing fields as zero.

    ``cache_status=unreported`` means the gateway did not send cache counters.
    A reported ``cached_tokens=0`` remains observable as a real zero.
    """
    values = usage if isinstance(usage, Mapping) else {}
    hit = _number(values.get("prompt_cache_hit_tokens"))
    miss = _number(values.get("prompt_cache_miss_tokens"))
    write = _number(values.get("prompt_cache_write_tokens"))
    reported = any(key in values for key in CACHE_TOKEN_KEYS)

    if hit is not None and miss is None:
        prompt = _number(values.get("prompt_tokens"))
        if prompt is not None:
            miss = max(0, prompt - hit)

    result: dict[str, Any] = {
        "cache_status": "unreported",
        "cache_hit_rate": None,
    }
    if hit is not None:
        result["prompt_cache_hit_tokens"] = hit
    if miss is not None:
        result["prompt_cache_miss_tokens"] = miss
    if write is not None:
        result["prompt_cache_write_tokens"] = write

    if hit is not None or miss is not None:
        hit_value = float(hit or 0)
        miss_value = float(miss or 0)
        denominator = hit_value + miss_value
        result["cache_hit_rate"] = round(hit_value / denominator, 6) if denominator else 0.0
        if denominator:
            result["cache_status"] = "hit" if hit_value > 0 else "miss"
        else:
            result["cache_status"] = "reported_zero"
    elif reported:
        result["cache_status"] = "reported"
    return result


def add_usage_totals(target: dict[str, int], usage: Mapping[str, Any] | None) -> None:
    """Add numeric usage counters while excluding derived cache rates/status."""
    if not isinstance(usage, Mapping):
        return
    for key in USAGE_TOKEN_KEYS:
        value = _number(usage.get(key))
        if value is not None:
            target[key] = target.get(key, 0) + int(value)


def aggregate_cache_summary(
    usages: Iterable[Mapping[str, Any]] | None,
    totals: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one cache summary for a complete task or a set of turns."""
    if totals is not None:
        summary = cache_summary(totals)
    else:
        combined: dict[str, int] = {}
        reported = False
        for usage in usages or ():
            item = cache_summary(usage)
            if item["cache_status"] != "unreported":
                reported = True
            add_usage_totals(combined, item)
        summary = cache_summary(combined)
        if not reported and summary["cache_status"] == "unreported":
            return summary
    if not summary.get("prompt_cache_hit_tokens") and "prompt_cache_hit_tokens" not in summary:
        summary.pop("prompt_cache_hit_tokens", None)
    if not summary.get("prompt_cache_miss_tokens") and "prompt_cache_miss_tokens" not in summary:
        summary.pop("prompt_cache_miss_tokens", None)
    if not summary.get("prompt_cache_write_tokens") and "prompt_cache_write_tokens" not in summary:
        summary.pop("prompt_cache_write_tokens", None)
    return summary


__all__ = [
    "CACHE_TOKEN_KEYS",
    "USAGE_TOKEN_KEYS",
    "add_usage_totals",
    "aggregate_cache_summary",
    "cache_summary",
]
