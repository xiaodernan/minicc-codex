"""M8-T806: minicc/pricing.py - pricing model tests.

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


def test_model_price_from_mapping_invalid() -> None:
    price = ModelPrice.from_mapping({"invalid": "data"})
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
    result = _fold("GPT-4")
    assert result == "gpt-4"


def test_fold_with_separators() -> None:
    result = _fold("a.b.c")
    assert result == "a-b-c"


# ============================================================================
# _tokens
# ============================================================================

def test_tokens_simple() -> None:
    result = _tokens({"prompt_tokens": 100}, "prompt_tokens")
    assert result == 100.0


def test_tokens_missing_key() -> None:
    result = _tokens({"other": 100}, "prompt_tokens")
    assert result == 0.0


def test_tokens_bool_value() -> None:
    result = _tokens({"prompt_tokens": True}, "prompt_tokens")
    assert result == 0.0


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
