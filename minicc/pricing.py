"""Per-model USD pricing for token usage (M4-T4).

The agent already counts tokens honestly (``llm/usage.py``) but never turned
them into money. This module owns the only price table in the codebase so that
``$/task`` can be reported next to ``tokens/task`` and the M6 fan-out guardrail
gets a dollar alarm rather than a token-only one.

Design rules:
  * Prices are USD per **1M tokens** (the unit every public price page uses).
  * A model is matched by its **longest known prefix**, case-insensitively, so
    ``claude-3-5-sonnet-20241022`` resolves through ``claude-3-5-sonnet``.
  * An **unknown model returns ``None``** — we never guess a price. A null cost
    is honest; a fabricated one is worse than no number at all.
  * The table can be extended at runtime with ``MINICC_PRICING_JSON`` so a
    deployment behind an internal gateway (or a test using the fake provider)
    can supply explicit prices without editing source.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "ModelPrice",
    "DEFAULT_PRICE_TABLE",
    "price_for",
    "cost_usd",
    "load_price_table",
]


@dataclass(frozen=True)
class ModelPrice:
    """USD per 1M tokens for one model family."""

    input_per_mtok: float
    output_per_mtok: float
    cache_read_per_mtok: float
    cache_write_per_mtok: float

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ModelPrice | None":
        try:
            return cls(
                input_per_mtok=float(raw["input"]),
                output_per_mtok=float(raw["output"]),
                cache_read_per_mtok=float(raw.get("cache_read", raw["input"])),
                cache_write_per_mtok=float(raw.get("cache_write", raw["input"])),
            )
        except (KeyError, TypeError, ValueError):
            return None


# Public list prices, USD per 1M tokens. Only models whose prices are published
# are listed; everything else resolves to None on purpose. The fictional default
# model (gpt-5.6-terra) is intentionally absent — deployments price it via
# MINICC_PRICING_JSON rather than shipping a made-up number here.
DEFAULT_PRICE_TABLE: dict[str, ModelPrice] = {
    "gpt-4o": ModelPrice(2.50, 10.00, 1.25, 2.50),
    "gpt-4o-mini": ModelPrice(0.15, 0.60, 0.075, 0.15),
    "gpt-4.1": ModelPrice(2.00, 8.00, 0.50, 2.00),
    "gpt-4.1-mini": ModelPrice(0.40, 1.60, 0.10, 0.40),
    "o1": ModelPrice(15.00, 60.00, 7.50, 15.00),
    "o3": ModelPrice(10.00, 40.00, 2.50, 10.00),
    "claude-3-5-sonnet": ModelPrice(3.00, 15.00, 0.30, 3.75),
    "claude-3-7-sonnet": ModelPrice(3.00, 15.00, 0.30, 3.75),
    "claude-3-5-haiku": ModelPrice(0.80, 4.00, 0.08, 1.00),
    "claude-opus-4": ModelPrice(15.00, 75.00, 1.50, 18.75),
}


def load_price_table() -> dict[str, ModelPrice]:
    """Default table merged with any ``MINICC_PRICING_JSON`` overrides.

    The env value is a JSON object mapping a model prefix to
    ``{"input": .., "output": .., "cache_read": .., "cache_write": ..}`` (USD
    per 1M tokens; cache fields default to the input price). Malformed entries
    are ignored rather than raising, so a bad override cannot break a run.
    """
    table = dict(DEFAULT_PRICE_TABLE)
    raw = os.getenv("MINICC_PRICING_JSON", "")
    if not raw.strip():
        return table
    try:
        override = json.loads(raw)
    except (ValueError, TypeError):
        return table
    if not isinstance(override, dict):
        return table
    for model, spec in override.items():
        if not isinstance(model, str) or not isinstance(spec, Mapping):
            continue
        price = ModelPrice.from_mapping(spec)
        if price is not None:
            table[model.strip().lower()] = price
    return table


def price_for(model: object, table: Mapping[str, ModelPrice] | None = None) -> ModelPrice | None:
    """Longest-prefix price lookup; ``None`` when the model is unknown."""
    name = str(model or "").strip().lower()
    if not name:
        return None
    prices = table if table is not None else load_price_table()
    best_key = ""
    best: ModelPrice | None = None
    for key, price in prices.items():
        if name.startswith(key) and len(key) > len(best_key):
            best_key, best = key, price
    return best


def _tokens(usage: Mapping[str, Any], key: str) -> float:
    value = usage.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return max(0.0, float(value))


def cost_usd(
    model: object,
    usage: Mapping[str, Any] | None,
    *,
    table: Mapping[str, ModelPrice] | None = None,
) -> float | None:
    """USD cost of one usage record, or ``None`` when the model is unpriced.

    ``prompt_tokens`` is the *total* prompt (cache hit + miss), so the hit
    portion is billed at the discounted ``cache_read`` rate and only the
    remainder at the full ``input`` rate. Cache-write tokens are billed
    separately. Returns ``None`` (not 0.0) for an unknown model so callers can
    distinguish "free" from "unpriced".
    """
    if not isinstance(usage, Mapping):
        return None
    price = price_for(model, table)
    if price is None:
        return None
    prompt = _tokens(usage, "prompt_tokens")
    hit = _tokens(usage, "prompt_cache_hit_tokens")
    write = _tokens(usage, "prompt_cache_write_tokens")
    completion = _tokens(usage, "completion_tokens")
    miss = max(0.0, prompt - hit)
    total = (
        miss * price.input_per_mtok
        + hit * price.cache_read_per_mtok
        + write * price.cache_write_per_mtok
        + completion * price.output_per_mtok
    ) / 1_000_000.0
    return round(total, 6)
