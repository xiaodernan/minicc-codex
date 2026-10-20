"""M8-T291 — 一个族只有一个键，**两边**都要折叠

价格表按"折叠后的族名"查找（``gpt-4.1`` 与 ``gpt-4-1`` 是同一个族）。
但折叠只做在了**覆盖项**上，公布表还是原样——于是同一族在表里有两个键，
而最长前缀的平局由字典顺序决定：公布的那一份排在前面，**部署自己的价格
被静默忽略**。

本门禁钉住：两种拼写都取到部署的价格；未知模型仍然没有价格。
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from minicc.pricing import load_price_table, price_for


def _override(monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]) -> None:
    monkeypatch.setenv("MINICC_PRICING_JSON", json.dumps(payload))


def test_a_dotted_spelling_keeps_the_deployment_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The published table spells it ``gpt-4.1``."""
    _override(monkeypatch, {"gpt-4.1": {"input": 99.0, "output": 99.0}})
    price = price_for("gpt-4.1", load_price_table())
    assert price is not None
    assert price.input_per_mtok == 99.0, (
        f"the deployment's own price was ignored: {price}"
    )


def test_the_dashed_spelling_reaches_the_same_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both spellings are one family."""
    _override(monkeypatch, {"gpt-4.1": {"input": 99.0, "output": 99.0}})
    price = price_for("gpt-4-1", load_price_table())
    assert price is not None
    assert price.input_per_mtok == 99.0, price


def test_a_different_spelling_reaches_the_same_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The case the fix was written for."""
    _override(monkeypatch, {"claude-3.5-sonnet": {"input": 77.0, "output": 77.0}})
    price = price_for("claude-3.5-sonnet", load_price_table())
    assert price is not None
    assert price.input_per_mtok == 77.0, price


def test_the_published_price_still_applies_without_an_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control: no override, the published price."""
    monkeypatch.delenv("MINICC_PRICING_JSON", raising=False)
    price = price_for("gpt-4.1", load_price_table())
    assert price is not None
    assert price.input_per_mtok == 2.0, price


def test_an_unknown_model_has_no_price(monkeypatch: pytest.MonkeyPatch) -> None:
    """The control: unknown models stay unpriced."""
    monkeypatch.delenv("MINICC_PRICING_JSON", raising=False)
    assert price_for("no-such-model", load_price_table()) is None
