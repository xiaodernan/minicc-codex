"""M8-T806/M8-T817: minicc/pricing.py - pricing model tests.

Tests for:
- ModelPrice: model price data class
- _SEPARATOR_FOLD: separator constant
- _fold: fold function
- load_price_table: load price table
- price_for: get price for model
- _tokens: token calculation
- cost_usd: calculate cost in USD
- ModelPrice.from_mapping: create from mapping
"""

from __future__ import annotations

import pytest

from minicc.pricing import (
    DEFAULT_PRICE_TABLE,
    ModelPrice,
    _SEPARATOR_FOLD,
    _fold,
    _tokens,
    cost_usd,
    load_price_table,
    price_for,
)


# ============================================================================
# ModelPrice
# ============================================================================

def test_model_price_creation() -> None:
    price = ModelPrice(
        input_per_mtok=0.01,
        output_per_mtok=0.03,
        cache_read_per_mtok=0.005,
        cache_write_per_mtok=0.01,
    )
    assert price.input_per_mtok == 0.01
    assert price.output_per_mtok == 0.03
    assert price.cache_read_per_mtok == 0.005
    assert price.cache_write_per_mtok == 0.01


def test_model_price_from_mapping() -> None:
    price = ModelPrice.from_mapping(
        {"input": 0.01, "output": 0.03, "cache_read": 0.005, "cache_write": 0.01}
    )
    assert price is not None
    assert price.input_per_mtok == 0.01
    assert price.output_per_mtok == 0.03


def test_model_price_from_mapping_cache_defaults() -> None:
    price = ModelPrice.from_mapping({"input": 0.10, "output": 0.20})
    assert price is not None
    assert price.cache_read_per_mtok == 0.10
    assert price.cache_write_per_mtok == 0.10


def test_model_price_from_mapping_invalid() -> None:
    price = ModelPrice.from_mapping({"invalid": "data"})
    assert price is None


def test_model_price_from_mapping_missing_input() -> None:
    price = ModelPrice.from_mapping({"output": 0.03})
    assert price is None


def test_model_price_from_mapping_missing_output() -> None:
    price = ModelPrice.from_mapping({"input": 0.01})
    assert price is None


# ============================================================================
# _SEPARATOR_FOLD
# ============================================================================

def test_separator_fold() -> None:
    assert isinstance(_SEPARATOR_FOLD, dict)
    assert len(_SEPARATOR_FOLD) > 0


# ============================================================================
# _fold
# ============================================================================

def test_fold_simple() -> None:
    assert _fold("GPT-4") == "gpt-4"


def test_fold_with_separators() -> None:
    assert _fold("a.b.c") == "a-b-c"


def test_fold_preserves_dash() -> None:
    assert _fold("gpt-4o-mini") == "gpt-4o-mini"


def test_fold_case_insensitive() -> None:
    assert _fold("CLAUDE-3-5-Sonnet") == "claude-3-5-sonnet"


def test_fold_underscore() -> None:
    assert _fold("a_b_c") == "a-b-c"


# ============================================================================
# _tokens
# ============================================================================

def test_tokens_simple() -> None:
    assert _tokens({"prompt_tokens": 100}, "prompt_tokens") == 100.0


def test_tokens_missing_key() -> None:
    assert _tokens({"other": 100}, "prompt_tokens") == 0.0


def test_tokens_bool_value() -> None:
    assert _tokens({"prompt_tokens": True}, "prompt_tokens") == 0.0


def test_tokens_negative_clamped() -> None:
    assert _tokens({"tokens": -50}, "tokens") == 0.0


def test_tokens_float_value() -> None:
    assert _tokens({"tokens": 12.5}, "tokens") == 12.5


def test_tokens_string_value() -> None:
    assert _tokens({"tokens": "100"}, "tokens") == 0.0


# ============================================================================
# load_price_table
# ============================================================================

def test_load_price_table() -> None:
    table = load_price_table()
    assert isinstance(table, dict)
    assert len(table) > 0


def test_default_price_table() -> None:
    assert isinstance(DEFAULT_PRICE_TABLE, dict)
    assert len(DEFAULT_PRICE_TABLE) > 0


def test_default_price_table_entries_valid() -> None:
    for model, price in DEFAULT_PRICE_TABLE.items():
        assert price.input_per_mtok >= 0
        assert price.output_per_mtok >= 0
        assert price.cache_read_per_mtok >= 0
        assert price.cache_write_per_mtok >= 0


# ============================================================================
# price_for
# ============================================================================

def test_price_for_known_model() -> None:
    price = price_for("gpt-4o")
    assert price is not None
    assert isinstance(price, ModelPrice)


def test_price_for_unknown_model() -> None:
    price = price_for("nonexistent-model-xyz")
    assert price is None


def test_price_for_prefix_match() -> None:
    price = price_for("gpt-4o-2024-11-20")
    assert price is not None
    assert isinstance(price, ModelPrice)


def test_price_for_case_insensitive() -> None:
    price = price_for("GPT-4O")
    assert price is not None


def test_price_for_none_model() -> None:
    assert price_for(None) is None


def test_price_for_empty_model() -> None:
    assert price_for("") is None


def test_price_for_mini_prefers_mini() -> None:
    mini = price_for("gpt-4o-mini")
    full = price_for("gpt-4o")
    assert mini is not None
    assert full is not None
    assert mini.input_per_mtok <= full.input_per_mtok


# ============================================================================
# cost_usd
# ============================================================================

def test_cost_usd_simple() -> None:
    cost = cost_usd("gpt-4o", {"prompt_tokens": 1000, "completion_tokens": 500})
    assert isinstance(cost, float)
    assert cost >= 0


def test_cost_usd_zero_tokens() -> None:
    cost = cost_usd("gpt-4o", {"prompt_tokens": 0, "completion_tokens": 0})
    assert cost == 0.0


def test_cost_usd_unknown_model() -> None:
    cost = cost_usd(
        "nonexistent-model-xyz",
        {"prompt_tokens": 1000, "completion_tokens": 500},
    )
    assert cost is None


def test_cost_usd_none_usage() -> None:
    assert cost_usd("gpt-4o", None) is None


def test_cost_usd_with_cache_read() -> None:
    usage = {
        "prompt_tokens": 100_000,
        "completion_tokens": 0,
        "prompt_cache_hit_tokens": 100_000,
        "prompt_cache_miss_tokens": 0,
    }
    cost = cost_usd("gpt-4o", usage)
    assert isinstance(cost, float)
    assert cost >= 0
    price = price_for("gpt-4o")
    expected = price.cache_read_per_mtok * 100_000 / 1_000_000
    assert cost == pytest.approx(expected, rel=1e-3)


def test_cost_usd_scales_linearly() -> None:
    usage = {"prompt_tokens": 1000, "completion_tokens": 1000}
    double = {"prompt_tokens": 2000, "completion_tokens": 2000}
    cost = cost_usd("gpt-4o", usage)
    cost_double = cost_usd("gpt-4o", double)
    assert cost_double >= cost > 0
