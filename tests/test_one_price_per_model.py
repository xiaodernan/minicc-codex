"""One published model must have one price (M8-T189).

Two tables price the same model in this codebase, and only one of them is read
by the money the user is shown:

  * ``minicc/pricing.py`` owns ``DEFAULT_PRICE_TABLE``, and
    ``TaskRecord.snapshot()`` -> ``pricing.cost_usd`` bills the **task card**;
  * ``minicc/agent/router.py`` keeps a second column of hand-typed rates on
    ``_DEFAULT_MODELS``, and ``StageRouter.estimate_cost`` -- which
    ``route_wiring._stage_cost_estimator`` feeds into ``Budget.record_cost`` --
    is what accrues toward the **run-budget dollar ceiling**.

Measured on the pre-fix bytes, one spend of 400k input / 60k output tokens:

  * ``o3`` accrues $12.80 into the budget while the card prints $6.40 -- the
    router's column says 20.00/80.00, the published table says 10.00/40.00;
  * ``claude-3.5-sonnet`` and ``claude-3.7-sonnet`` accrue $2.10 each and the
    card prints ``None``: the table keys those families with hyphens
    (``claude-3-5-sonnet``) and the prefix rule only ever folded case;
  * ``claude-3-haiku`` accrues $0.175 and the card prints ``None``: the table
    has no row for that family at all.

``gpt-4.1`` reads $1.28 on both sides for THIS usage because it has no cache
tokens: its two cache channels do differ (1.00 read on the router's side, 0.50
published), which is the shape of what a divergence looks like when nobody
routes it yet.

A fourth face is the route that prices nothing at all: ``estimate_cost`` stopped
at ``if not model: return 0.0``, so a stage routed to a published family the
built-in registry never lists (``gpt-4.1-mini``) accrued $0.00 toward its dollar
ceiling while the task card billed it $0.256 -- an un-accrued spend can only
trip the cap late, never early.

The fix is one owner: the published table. The dollar ceiling keeps honouring a
deployment's own ``custom_models`` price column -- that is the operator's number
for a gateway model no public table can know, and a declared zero keeps meaning
"free" rather than "unknown" -- and keeps pricing nothing it does not know
(``0.0`` means "no price", which ``_stage_cost_estimator`` documents as degrading
the ceiling to not-enforced rather than guessing).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import minicc
from minicc import pricing
from minicc.agent import router as router_module
from minicc.agent.router import StageRouter
from minicc.route_wiring import _stage_cost_estimator

REPO = Path(minicc.__file__).resolve().parents[1]
ROUTER_FILE = REPO / "minicc" / "agent" / "router.py"

INPUT_TOKENS = 400_000
OUTPUT_TOKENS = 60_000
USAGE = {"prompt_tokens": INPUT_TOKENS, "completion_tokens": OUTPUT_TOKENS}
ZERO = (0.0, 0.0, 0.0, 0.0)


def _routed(name: str) -> StageRouter:
    """A router whose only stage routes to ``name`` through the shipped seam."""
    return StageRouter(
        name,
        100.0,
        stage_routing_config={
            "enabled": True,
            "stage_map": {"census": "fast"},
            "tiers": {"fast": [name]},
        },
    )


def _ceiling_usd(name: str, usage: dict[str, int] | None = None) -> float:
    """What one spend accrues toward the run budget's dollar ceiling."""
    return _stage_cost_estimator(_routed(name), "census")(dict(usage or USAGE))


def _card_usd(name: str, usage: dict[str, int] | None = None) -> float | None:
    """What the same spend prints on the task's own cost line."""
    return pricing.cost_usd(name, dict(usage or USAGE))


def _routable_published_names() -> list[str]:
    """Every model name the shipped router can select without any config."""
    names = list(router_module._DEFAULT_MODELS)
    tree = ast.parse(ROUTER_FILE.read_text(encoding="utf-8"), filename=str(ROUTER_FILE))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and any(getattr(target, "id", "") == "defaults" for target in node.targets)
            and isinstance(node.value, ast.Dict)
        ):
            for element in node.value.values:
                if isinstance(element, ast.List):
                    names.extend(
                        item.value for item in element.elts if isinstance(item, ast.Constant)
                    )
    return sorted(set(names))


def test_the_registry_column_is_not_a_second_price_table() -> None:
    """``minicc.pricing`` owns published rates, so the registry carries none.

    Hand-typed rates here are what let the ceiling and the card diverge. This is
    the rebound clause: restore the column and it goes red while every
    behavioural clause below can stay green, because the two agree again only
    as long as nothing re-reads the copy.
    """
    carried = {
        name: tuple(cfg.cost_usd_per_1m)
        for name, cfg in router_module._DEFAULT_MODELS.items()
        if tuple(cfg.cost_usd_per_1m) != ZERO
    }
    assert not carried, (
        "内置注册表又自己带上了价格列，同一个模型就有两个主人了：%r" % (carried,)
    )


def test_one_spend_bills_the_same_dollars_into_the_ceiling_and_onto_the_card() -> None:
    """For every routable published model, the two money surfaces are one number.

    The population is derived from the router, not from this file: a published
    name whose price only one of the two surfaces can reach is the defect.
    """
    names = _routable_published_names()
    assert len(names) >= 8 and "o3" in names and "claude-3-haiku" in names, (
        "路由得到的公开模型名单缩水了（%d 条：%s），这条普查就不再量它说的那件事"
        % (len(names), names)
    )
    rows = []
    for name in names:
        ceiling = _ceiling_usd(name)
        card = _card_usd(name)
        if card is None:
            rows.append((name, ceiling, "card=unpriced(None)"))
        elif abs(ceiling - card) > 1e-9:
            rows.append((name, ceiling, "card=%.6f" % card))
    assert not rows, (
        "同一笔 400k/60k 花费在两个表面的美元不一样（模型, 计入预算顶格, 任务卡）：%r" % (rows,)
    )
    assert _card_usd("o3") == pytest.approx(6.4), (
        "o3 的公布价不再是 10.00/40.00 每百万，这条普查的参照物变了，"
        "实测卡片=%r（顶格=%r）" % (_card_usd("o3"), _ceiling_usd("o3"))
    )


def test_the_published_name_the_router_writes_is_a_name_the_table_can_read() -> None:
    """Every routable name resolves to a price, in the spelling it is routed under.

    The prefix rule folded case but not separators, so the router's dotted
    ``claude-3.5-sonnet`` was a name the published table could not see, and a
    spend on it billed the run while every report said "unpriced".
    """
    unpriced = [name for name in _routable_published_names() if pricing.price_for(name) is None]
    assert not unpriced, (
        "路由得到的模型名在唯一那张价表里读不到价，报表只能说未计价：%r" % (unpriced,)
    )


def test_a_declared_gateway_price_stays_the_operators_number() -> None:
    """A deployment that writes its own column wins over the published table.

    ``custom_models`` exists so an internal gateway can be priced; if the ceiling
    started ignoring that column, every operator-priced model would silently stop
    accruing anything toward its dollar cap.
    """
    config = {
        "enabled": True,
        "stage_map": {"census": "fast"},
        "tiers": {"fast": ["gpt-4o"]},
        "custom_models": {"gpt-4o": {"tier": "fast", "cost_usd_per_1m": [0.01, 0.02, 0.0, 0.0]}},
    }
    accrued = _stage_cost_estimator(
        StageRouter("gpt-4o", 100.0, stage_routing_config=config), "census"
    )(dict(USAGE))
    assert accrued == pytest.approx(
        (INPUT_TOKENS * 0.01 + OUTPUT_TOKENS * 0.02) / 1_000_000
    ), "部署自己声明的价格没有生效（它应当盖住公布价），实测 %r" % (accrued,)


def test_a_custom_row_that_declares_no_price_does_not_silence_the_published_one() -> None:
    """Overriding a family's tier or base_url must not erase its price.

    ``custom_models`` is how a deployment pins provider details for a published
    model. Treating every custom row as a price declaration makes an absent
    column read as "free", which turns a dollar ceiling off without anyone
    writing the word.
    """
    config = {
        "enabled": True,
        "stage_map": {"census": "fast"},
        "tiers": {"fast": ["gpt-4o"]},
        "custom_models": {"gpt-4o": {"tier": "fast", "base_url": "http://127.0.0.1:8000/v1"}},
    }
    accrued = _stage_cost_estimator(
        StageRouter("gpt-4o", 100.0, stage_routing_config=config), "census"
    )(dict(USAGE))
    card = _card_usd("gpt-4o")
    assert accrued == pytest.approx(card) and accrued > 0.0, (
        "只声明了 tier/base_url 的一行把公布价吃掉了：顶格计 %r，卡片 %r" % (accrued, card)
    )


def test_a_published_rate_change_moves_the_ceiling_to_the_new_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ceiling must read the table live, not a copy taken at construction.

    ``MINICC_PRICING_JSON`` exists so a deployment can restate a price without
    editing source. If the ceiling keeps its own column, that env change moves
    the task card only, and the dollar cap quietly governs a different price.
    """
    monkeypatch.setenv(
        "MINICC_PRICING_JSON", json.dumps({"gpt-4o": {"input": 1000.0, "output": 1000.0}})
    )
    accrued = _ceiling_usd("gpt-4o")
    expected = (INPUT_TOKENS + OUTPUT_TOKENS) * 1000.0 / 1_000_000
    assert accrued == pytest.approx(expected), (
        "改表没有改到顶格这一侧（应当 %r，实测 %r）——那一侧读的是另一张表"
        % (expected, accrued)
    )
    assert accrued == pytest.approx(_card_usd("gpt-4o")), (
        "改表后两个表面又分开了：顶格 %r，卡片 %r" % (accrued, _card_usd("gpt-4o"))
    )


def test_a_routed_model_the_registry_never_heard_of_is_still_priced_by_the_table() -> None:
    """A tier may name any published model; being unregistered is not "free".

    ``custom_models`` and the tier lists can route a stage to a family the built-in
    registry never lists (``gpt-4.1-mini``). The table prices it and the task card
    bills it, while ``estimate_cost`` used to stop at ``if not model: return 0.0``:
    such a run accrued nothing toward its dollar ceiling however much it spent. The
    fourth face of this defect, and the unsafe direction -- an accrued-0 spend can
    only ever trip late, never early.
    """
    assert "gpt-4.1-mini" not in router_module._DEFAULT_MODELS, (
        "前提变了：gpt-4.1-mini 已经在内置注册表里，这一格量的就不再是"
        "「未登记但已公布」那条路径（实测名单 %s）"
        % (sorted(router_module._DEFAULT_MODELS),)
    )
    card = _card_usd("gpt-4.1-mini")
    accrued = _ceiling_usd("gpt-4.1-mini")
    assert card is not None and accrued > 0.0 and abs(accrued - card) <= 1e-9, (
        "路由得到、价表认得、卡片计价的模型在顶格一侧计 %r（卡片 %r），"
        "那它的美元上限永远不会触发" % (accrued, card)
    )


def test_the_ceiling_is_conservative_for_cache_tokens_and_never_reads_below_the_card() -> None:
    """The documented direction of the estimate stays the safe one.

    ``_stage_cost_estimator`` multiplies the flat input rate over the whole
    prompt, so a cache-heavy spend accrues AT LEAST what the card bills: the cap
    can trip early, never late. This pins that moving to one owner did not turn
    the ceiling into an under-biller.
    """
    heavy = {
        "prompt_tokens": INPUT_TOKENS,
        "completion_tokens": OUTPUT_TOKENS,
        "prompt_cache_hit_tokens": 300_000,
        "prompt_cache_write_tokens": 50_000,
    }
    price = pricing.price_for("gpt-4o")
    assert price is not None and price.cache_read_per_mtok < price.input_per_mtok, (
        "参照物没了：gpt-4o 的缓存读价不再低于输入价，这条方向见证量不到任何东西"
    )
    card = _card_usd("gpt-4o", heavy)
    ceiling = _ceiling_usd("gpt-4o", heavy)
    assert card is not None and ceiling >= card, (
        "顶格一侧反而比卡片少收（%r < %r），那它就不是保守估计而是放行器" % (ceiling, card)
    )
    assert ceiling > card, (
        "有缓存命中的用量两侧算出同一个数（%r），说明缓存通道没有被卡片读到，"
        "这一格没有在量它说的方向" % (ceiling,)
    )
