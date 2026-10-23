"""Usage normalization shared by providers, agent runs, and task snapshots."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from math import isfinite
from typing import Any

from ..trace import trace_event
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


def channel_counter() -> dict[str, int]:
    """The zeroed shape of one channel's running usage counters.

    ``requests`` counts the calls made on a channel, ``total_tokens``
    sums what they reported.  This is **not** a usage record: it is the
    per-channel accumulator the two gateway providers keep beside their
    client (``_channel_usage``), seeded in ``__init__`` for both channels
    and re-seeded by ``setdefault`` when a channel appears at runtime.
    Six hand-written copies of this shape lived in those two files - a
    key one copy forgets is a channel whose counter the readers of
    ``_channel_usage`` see as missing that counter.

    A constructor, never a constant: the ``__init__`` seeds for ``paid``
    and ``plan`` must be distinct objects, or switching channels would
    accumulate into one shared counter.
    """
    return {"requests": 0, "total_tokens": 0}


def channel_status_payload(
    active: str, plan_available: bool, usage: Mapping[str, Any]
) -> dict[str, Any]:
    """The three-key shape of a provider's channel snapshot.

    The two gateway providers both expose ``channel_status()`` and the
    CLI ``/status`` and the web metrics route both read the result.  A
    key one provider forgets is a reader that sees the channel state as
    a missing field; a counter handed out without ``dict(...)`` is a
    reader that can mutate the provider's live accumulator.  The copy
    lives here so neither provider can skip it.
    """
    return {
        "active": active,
        "plan_available": plan_available,
        "usage": {name: dict(counter) for name, counter in usage.items()},
    }


CHANNEL_SWITCHED_CODE = "provider_channel_switched"
CHANNEL_SWITCHED_SUMMARY = "主通道额度已用尽（402/Credit 上限），本次任务改用 Step Plan 套餐通道"


def channel_switched_event(status_code: Any, error_type: str | None = None) -> dict[str, Any]:
    """The trace event both gateway providers emit when the paid pool runs dry.

    A 402 (or a credit-flavoured 429) means the paid channel's quota pool is
    empty: with a plan channel configured the provider switches mid-task and
    says so with this one event.  Both gateway providers used to spell the
    whole event by hand - a summary one copy forgets to update is a UI that
    explains the switch with last quarter's wording, and a code one copy
    drifts on is a reader (the task event stream) that stops finding the
    switch at all.

    ``error_type`` is the one field only the OpenAI-compatible wire carries:
    its quota verdict arrives as an exception, so the class name rides along.
    The key order is the one both call sites already emitted, so no reader
    sees a reordered payload.
    """
    detail: dict[str, Any] = {"from": "paid", "to": "plan"}
    if error_type is not None:
        detail["error_type"] = error_type
    detail["status_code"] = status_code
    return trace_event(
        name="provider",
        status="ok",
        phase="planning",
        code=CHANNEL_SWITCHED_CODE,
        summary=CHANNEL_SWITCHED_SUMMARY,
        detail=detail,
    )


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
    "CHANNEL_SWITCHED_CODE",
    "CHANNEL_SWITCHED_SUMMARY",
    "USAGE_TOKEN_KEYS",
    "add_usage_totals",
    "aggregate_cache_summary",
    "cache_summary",
    "channel_counter",
    "channel_status_payload",
    "channel_switched_event",
]
