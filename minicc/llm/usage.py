"""Usage normalization shared by providers, agent runs, and task snapshots."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from math import isfinite
from typing import Any

from .base import safe_int


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


def measured_usage(
    prompt_tokens: int, completion_tokens: int, total_tokens: int | None = None
) -> dict[str, Any]:
    """The three-key shape of a usage record the gateway actually reported.

    The sibling of ``estimated_usage``: same three counters, but these came
    off a wire instead of being counted locally.  ``total`` defaults to the
    sum of its parts because that is what every writer meant by it - the
    fake provider's fixture rows spell the arithmetic out in a comment and
    the Anthropic normalizer adds the total on a second line, and a row
    whose total disagrees with its parts is a lie the cost pipeline bills
    without complaint.
    """
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": (
            total_tokens if total_tokens is not None
            else prompt_tokens + completion_tokens
        ),
    }


def estimated_usage(prompt_tokens: int, completion_tokens: int) -> dict[str, Any]:
    """The four-key shape of an estimated usage record.

    Two readers wrote it by hand - the agent loop (a gateway that answers
    without usage) and the web planner route (a planner call that rides
    outside the loop).  A key one side forgets is a usage record the
    aggregation reads as a missing field.
    """
    return {**measured_usage(prompt_tokens, completion_tokens), "estimated": True}


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and isfinite(value):
        return value
    return None


def token_count(value: Any, default: int | None = None) -> int | None:
    """Read a token counter a gateway may have sent malformed.

    M8-T358: a counter is **untrusted input** - a dict, a list or a
    non-numeric string used to raise out of the provider and kill the turn
    on one wire, while the other wire simply ignored it.  One home, two
    defaults: ``None`` means "not reported" (the OpenAI-compatible wire
    omits the key), ``0`` means "reported as nothing" (the Anthropic
    wire's convention).

    The conversion is ``int(...)`` exactly as before - a numeric string
    still reads as a number ✓ - so the only change is that a value that
    cannot be read no longer raises.
    """
    return safe_int(value, default)


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

    if hit is not None and miss is not None:
        hit_value = float(hit)
        miss_value = float(miss)
        denominator = hit_value + miss_value
        result["cache_hit_rate"] = round(hit_value / denominator, 6) if denominator else 0.0
        if denominator:
            result["cache_status"] = "hit" if hit_value > 0 else "miss"
        else:
            result["cache_status"] = "reported_zero"
    elif hit is not None or miss is not None:
        # M8-T326: only **one** side was reported.  The other one is not
        # zero - it is *unknown* - and treating it as zero fabricates a
        # rate that was never observed (``{"prompt_cache_hit_tokens": 100}``
        # used to report a 100% hit rate).  The function's own contract says
        # it does not treat missing fields as zero; this is where it did.
        result["cache_status"] = "partial"
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
