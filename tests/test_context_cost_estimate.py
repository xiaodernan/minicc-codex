# -*- coding: utf-8 -*-
"""M8-T1318 — a deep-context cost warning must use the real price table."""

from __future__ import annotations

import minicc.pricing as pricing
import minicc.rag as rag


def test_unknown_model_is_unpriced_not_zero():
    out = rag.estimate_context_cost_usd("no-such-model-xyz", {"estimated_tokens": 50000}, 700)
    assert out["usd"] is None
    assert "unpriced" in out["basis"]
    assert out["prompt_tokens"] == 50000


def test_priced_model_uses_the_ledger_price_table(monkeypatch):
    # gpt-4o is 2.50 / 10.00 per 1M in the shipped table — the same one the
    # task ledger bills with. A 50k prompt + 700 output must be ~0.1325 USD.
    monkeypatch.setattr(pricing, "load_price_table", lambda: pricing.DEFAULT_PRICE_TABLE)
    out = rag.estimate_context_cost_usd("gpt-4o", {"estimated_tokens": 50000}, 700)
    expected = 50000 / 1_000_000 * 2.50 + 700 / 1_000_000 * 10.00
    assert out["usd"] is not None and abs(out["usd"] - expected) < 1e-9
    assert out["basis"].startswith("upper estimate")


def test_cost_estimate_is_an_upper_bound_without_cache_credit(monkeypatch):
    monkeypatch.setattr(pricing, "load_price_table", lambda: pricing.DEFAULT_PRICE_TABLE)
    out = rag.estimate_context_cost_usd("gpt-4o", {"estimated_tokens": 8000}, 700)
    assert out["usd"] is not None and out["usd"] > 0
    # Doubling the prompt doubles the input portion — the estimate scales.
    bigger = rag.estimate_context_cost_usd("gpt-4o", {"estimated_tokens": 16000}, 700)
    assert bigger["usd"] > out["usd"]


def test_answer_budget_path_carries_cost_estimate(monkeypatch):
    from types import SimpleNamespace

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    class _Msg:
                        content = "ok [1]."
                    class _Usage:
                        prompt_tokens = 100
                        completion_tokens = 2
                        total_tokens = 102
                        prompt_tokens_details = None
                    class _Choice:
                        message = _Msg()
                    class _Resp:
                        pass
                    resp = _Resp(); resp.choices = [_Choice()]; resp.usage = _Usage()
                    return resp

    monkeypatch.setattr("openai.OpenAI", _Client)
    monkeypatch.setattr(pricing, "load_price_table", lambda: pricing.DEFAULT_PRICE_TABLE)
    out = rag.answer("缓存", config=SimpleNamespace(
        model="gpt-4o", base_url="https://example.invalid/v1", api_key="sk-test", prompt_cache_key=""),
        budget_tokens=2000)
    assert "cost_estimate" in out["context"]
    assert out["context"]["cost_estimate"]["usd"] is not None
    assert out["context"]["cost_estimate"]["prompt_tokens"] > 0
