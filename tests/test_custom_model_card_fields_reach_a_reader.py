"""M8-T195: a ``custom_models`` key an operator writes must reach a reader, or be named unread.

``minicc/config.py`` validates a ``stage_routing.custom_models`` entry against
``_CUSTOM_MODEL_KEYS`` and refuses anything else by name, so the vocabulary a
deployment may write is policed.  ``StageRouter._register_custom_models`` then
stores every admitted key on a ``ModelConfig`` card.  Neither fact says a stored
field is ever *asked*, and the validator's own refusal text promises exactly the
opposite: a key with no reader "写在这里等于让它静默失效".  So this file asks what
nobody asks: for each field a card can hold, do two cards that differ only in
that field make the router or the wiring answer differently?

Measured, and the register below is that measurement: five of ten fields change
nothing (``tier``, ``max_tokens``, ``supports_tools``, ``supports_vision``,
``supports_reasoning_effort``); ``provider``, ``base_url``, ``api_key_env``,
``cost_usd_per_1m`` and ``name`` do.  Wiring a reader for a register field is a
routing or request-shape change that has not been approved - ``tier`` would make
``stage_routing.tiers`` select by capability instead of by name, ``max_tokens``
would push a registry value into the outgoing request body, and the three
``supports_*`` flags would let a capability claim gate behaviour - so this file is
the register such a wiring must edit in the same commit, and
``test_the_census_sees_reads_and_refuses_to_be_blind`` is what stops the register
from being kept honest by a walk that has quietly stopped seeing reads.

Config validation is not a reader: the validator checks a value's *shape*, which
is why a wrong type is refused here by the shipped function rather than
re-implemented.  A name-only search would lie in both directions - ``.max_tokens``
also lives on ``Budget``, ``.tier`` on ``SubAgent``, and ``fallback_models``
contains the substring ``_models`` - so holders are resolved structurally.
"""

from __future__ import annotations

import ast
import dataclasses
import os
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest

from minicc import config as minicc_config
from minicc import route_wiring
from minicc.agent.router import ModelConfig, ModelTier, StageRouter

REPO = Path(__file__).resolve().parents[1]
PKG = REPO / "minicc"

MODEL = "gw-t195"
STAGES = ("planning", "inspect", "implement", "verify", "repair", "review")
KEY_SET = "MINICC_T195_KEY_SET"
KEY_UNSET = "MINICC_T195_KEY_UNSET"

BASE_CARD = {
    "tier": "balanced",
    "provider": "openai_compatible",
    "base_url": "https://base.example/v1",
    "api_key_env": KEY_SET,
    "cost_usd_per_1m": [1.0, 2.0, 0.0, 0.0],
    "max_tokens": 8192,
    "supports_tools": True,
    "supports_vision": False,
    "supports_reasoning_effort": False,
}

# Two admitted values per writable field: a pair an operator could actually
# write, differing in that one key and nothing else.
_MUTATIONS: dict[str, tuple[object, object]] = {
    "tier": ("fast", "reasoning"),
    "provider": ("openai", "anthropic"),
    "base_url": ("https://a.example/v1", "https://b.example/v1"),
    "api_key_env": (KEY_SET, KEY_UNSET),
    "cost_usd_per_1m": ([1.0, 2.0, 0.0, 0.0], [8.0, 16.0, 1.0, 0.5]),
    "max_tokens": (4096, 32768),
    "supports_tools": (True, False),
    "supports_vision": (False, True),
    "supports_reasoning_effort": (False, True),
}

# The measurement this file keeps honest.  Each reason names what would have to
# change for the field to be consulted - which is the decision not yet taken.
_UNREAD_REGISTER: dict[str, str] = {
    "tier": (
        "选模型靠 stage_routing.tiers 的名字表与注册表成员（_select_model_for_tier），"
        "卡片上的 tier 从未被问过；改成按能力挑选是路由口径决策，未批"
    ),
    "max_tokens": (
        "出站请求的 max_tokens 由 provider 层与 Budget 自己的参数决定，"
        "注册表卡片没把它接进请求；接线会改变请求体形状，未批"
    ),
    "supports_tools": (
        "卡片声明能力，请求构造不问能力；把 False 变成「本轮不发 tools」是行为改变，未批"
    ),
    "supports_vision": (
        "同上：某个 stage 是否带图像由调用方决定，能力位无读者（M8-T190 量的就是这条）"
    ),
    "supports_reasoning_effort": (
        "effort 名字来自 stage_routing.reasoning_effort，卡片的能力位只是元数据；"
        "内置表里 o1/o3/claude 那几行写的 True 同样没人问过"
    ),
}


# -- the three vocabularies --------------------------------------------------


def _card_fields() -> tuple[str, ...]:
    return tuple(field.name for field in dataclasses.fields(ModelConfig))


def _writer_kwargs() -> set[str]:
    """The keyword names ``_register_custom_models`` hands to ``ModelConfig``."""
    tree = ast.parse((PKG / "agent" / "router.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_register_custom_models":
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Name)
                    and inner.func.id == "ModelConfig"
                ):
                    return {keyword.arg for keyword in inner.keywords if keyword.arg}
    raise AssertionError("no ModelConfig(...) construction inside _register_custom_models")


def _admitted_keys() -> frozenset[str]:
    return minicc_config._CUSTOM_MODEL_KEYS


# -- the reader census -------------------------------------------------------


def _produces_card(expr: ast.expr) -> bool:
    """Does this expression obtain a ``ModelConfig`` (structurally, not by name)?"""
    for node in ast.walk(expr):
        if isinstance(node, ast.Attribute) and node.attr in {"model_config", "_models"}:
            return True
        if isinstance(node, ast.Name) and node.id == "ModelConfig":
            return True
    return False


def _holder_names(tree: ast.AST) -> set[str]:
    """Names this module binds to a card: assignment, annotation, or loop target."""
    holders: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _produces_card(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    holders.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if _annotates_card(node.annotation):
                holders.add(node.target.id)
        elif isinstance(node, ast.For) and _produces_card(node.iter):
            elements = node.target.elts if isinstance(node.target, ast.Tuple) else [node.target]
            for element in elements:
                if isinstance(element, ast.Name):
                    holders.add(element.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for argument in [*node.args.args, *node.args.kwonlyargs]:
                if _annotates_card(argument.annotation):
                    holders.add(argument.arg)
    return holders


def _annotates_card(annotation: ast.expr | None) -> bool:
    return annotation is not None and ast.unparse(annotation) in {
        "ModelConfig",
        "ModelConfig | None",
        "Optional[ModelConfig]",
    }


def _card_reads(tree: ast.AST) -> tuple[list[str], list[str]]:
    """``(lexical reads, dynamic reads)`` of a card in this module.

    A dynamic read (``getattr(card, ...)``, ``asdict(card)``, ``vars(card)``) is
    reported separately instead of counted: the walk cannot see which field it
    names, so a file that reads cards that way makes the census blind, and a
    blind census must fail by name rather than certify an empty unread set.
    """
    holders = _holder_names(tree)
    lexical: list[str] = []
    dynamic: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            if isinstance(node.value, ast.Name) and node.value.id in holders:
                lexical.append(node.attr)
            elif _produces_card(node.value) and isinstance(node.value, ast.Call):
                # `self._models.get(name).provider`: the card is built inline.
                lexical.append(node.attr)
            continue
        if not isinstance(node, ast.Call):
            continue
        callee = ast.unparse(node.func)
        if not node.args:
            continue
        first = ast.unparse(node.args[0])
        if callee in {"getattr", "setattr", "hasattr", "delattr"} and first in holders:
            dynamic.append(callee)
        elif callee in {"asdict", "vars"} and first in holders:
            dynamic.append(callee)
    return lexical, dynamic


@lru_cache(maxsize=1)
def _census() -> tuple[dict[str, int], list[str], int]:
    """Read counts per field name, every dynamic site, and the number of files walked.

    Cached because four cases ask this one question: the walk parses every module
    under ``minicc/``, and a second pass would add cost without new evidence.
    """
    counts: dict[str, int] = {}
    dynamic: list[str] = []
    files = 0
    for path in sorted(PKG.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        files += 1
        lexical, hits = _card_reads(tree)
        for attr in lexical:
            counts[attr] = counts.get(attr, 0) + 1
        for name in hits:
            dynamic.append("%s (%s)" % (path.relative_to(REPO).as_posix(), name))
    return counts, dynamic, files


_POSITIVE_FIXTURE = """
from minicc.agent.router import ModelConfig, ModelTier


def build(stage_router, name):
    card = stage_router.model_config(name)
    other = stage_router._models.get(name)
    built = ModelConfig("m", ModelTier.FAST, "openai")
    for entry in stage_router._models.values():
        print(entry.supports_vision)
    return card.max_tokens + other.tier + built.supports_tools
"""

_NEGATIVE_FIXTURE = """
class Budget:
    max_tokens = 0


def use(budget, tier, fallback_models):
    index = min(0, len(fallback_models) - 1)
    return budget.max_tokens + tier.tier + fallback_models[index].provider
"""


def _fixture_reads(source: str) -> set[str]:
    return set(_card_reads(ast.parse(source))[0])


# -- the behavioural reading -------------------------------------------------


@contextmanager
def _env(**values: str):
    saved = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value == "__UNSET__":
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _deployment() -> SimpleNamespace:
    return SimpleNamespace(
        api_key="deployment-key",
        base_url="https://deploy.example/v1",
        provider_type="openai",
        anthropic_base_url="https://anthropic.deploy.example",
    )


def _answer(field: str, value: object) -> dict:
    """Everything a card can decide, for a card whose only difference is one field."""
    card = dict(BASE_CARD)
    card[field] = value
    router = StageRouter(
        MODEL,
        100.0,
        stage_routing_config={
            "enabled": True,
            "tiers": {tier: [MODEL] for tier in ("fast", "balanced", "reasoning")},
            "stage_map": {stage: "balanced" for stage in STAGES},
            "cost_limits_usd": {"implement": 0.5},
            "custom_models": {MODEL: card},
        },
    )
    with _env(**{KEY_SET: "from-env", KEY_UNSET: "__UNSET__"}):
        routes = {stage: router.route(stage).to_dict() for stage in STAGES}
        costs = [
            router.estimate_cost(stage, 400_000, 60_000, 10_000, 1_000) for stage in STAGES
        ]
        wired: list[object] = []
        try:
            wired.append(route_wiring._route_provider_spec(router, MODEL, _deployment()))
        except minicc_config.ConfigError as exc:
            wired.append(("ConfigError", str(exc)))
    return {"routes": routes, "costs": costs, "wired": wired}


@lru_cache(maxsize=1)
def _behaviour_reads() -> frozenset[str]:
    """Fields whose two admitted values produce two different answers."""
    return frozenset(
        field
        for field, (first, second) in _MUTATIONS.items()
        if _answer(field, first) != _answer(field, second)
    )


@lru_cache(maxsize=1)
def _name_read_by_the_refusal() -> bool:
    """Does the refusal come from the card's ``name`` or from the registry key?

    The two are the same string for every card an operator can write, so the
    only way to tell the readers apart is to register a card under a key that
    does not match its own ``name`` and see which one the message prints.
    """
    router = StageRouter(MODEL, 100.0, stage_routing_config={"enabled": True})
    router._models[MODEL] = ModelConfig(
        name="card-says-this", tier=ModelTier.BALANCED, provider="anthropicx"
    )
    try:
        route_wiring._route_provider_spec(router, MODEL, _deployment())
    except minicc_config.ConfigError as exc:
        return "card-says-this" in str(exc)
    return False


# -- the door ---------------------------------------------------------------


def test_the_admitted_keys_the_writer_kwargs_and_the_card_are_one_set() -> None:
    """What the validator admits, what the card declares, what the writer stores.

    Three lists that only look the same.  A key the validator admits and the
    writer never passes is dropped at registration without a word; a writer
    kwarg the card does not declare raises ``TypeError`` on the request path.
    ``name`` is the one card field an operator cannot write - it is the registry
    key - so it is exempt here and tested for a reader below.
    """
    admitted = _admitted_keys()
    declared = set(_card_fields())
    written = _writer_kwargs()
    assert admitted - declared == set(), (
        "config admits %s, which no card can hold: the key validates, then "
        "ModelConfig() raises on the request path" % sorted(admitted - declared)
    )
    assert written - declared == set(), (
        "_register_custom_models passes %s, which ModelConfig does not declare"
        % sorted(written - declared)
    )
    assert admitted == written - {"name"}, (
        "the vocabulary the validator polices (%s) and the columns the writer "
        "actually stores (%s) have drifted; a key in only one of the two is a "
        "silently-dead knob or an unstorable promise"
        % (sorted(admitted), sorted(written - {"name"}))
    )
    assert declared - admitted - {"name"} == set(), (
        "the card declares %s, which no operator can write and nothing here "
        "explains" % sorted(declared - admitted - {"name"})
    )
    # The belt is the shipped validator's own, not a restatement of it: every
    # admitted key is type-checked, so a dict value must be refused by name.
    for key in sorted(admitted):
        with pytest.raises(minicc_config.ConfigError):
            minicc_config.normalize_stage_routing(
                {"enabled": True, "custom_models": {MODEL: {key: {"nested": 1}}}}
            )
    with pytest.raises(minicc_config.ConfigError):
        minicc_config.normalize_stage_routing(
            {"enabled": True, "custom_models": {MODEL: {"supports_audio": True}}}
        )


def test_every_card_field_either_reaches_a_reader_or_is_named_unread() -> None:
    """The register is the measurement, checked in both directions.

    An entry named while something reads it rots into an excuse; an unread field
    missing from the register is a knob nobody will notice is dead.  The lexical
    census and the behavioural reading must also agree with each other - if a
    read exists that only one of the two can see, neither can be trusted.
    """
    counts, dynamic, _files = _census()
    unread_lexical = {field for field in _card_fields() if counts.get(field, 0) == 0}
    read_behaviourally = _behaviour_reads() | (
        {"name"} if _name_read_by_the_refusal() else set()
    )
    unread_behavioural = set(_card_fields()) - read_behaviourally
    assert set(_UNREAD_REGISTER) == unread_lexical, (
        "the register names %s unread, the census says %s - one of the two is "
        "stale, and a reader wired since landing belongs in the same commit as "
        "the retired register entry"
        % (sorted(_UNREAD_REGISTER), sorted(unread_lexical))
    )
    assert set(_UNREAD_REGISTER) == unread_behavioural, (
        "the register and the router's own answers disagree: behaviour reads "
        "%s as unread while the register says %s"
        % (sorted(unread_behavioural), sorted(_UNREAD_REGISTER))
    )
    assert unread_lexical == unread_behavioural, (
        "the census and the behaviour disagree field by field: only the census "
        "sees a reader for %s, only the behaviour does for %s - a name-shape "
        "match or a dynamic read is hiding in one of them"
        % (sorted(unread_behavioural - unread_lexical), sorted(unread_lexical - unread_behavioural))
    )
    for field, reason in sorted(_UNREAD_REGISTER.items()):
        assert reason.strip(), "%s is registered unread with no reason" % field
        assert len(reason) > 30, "%s's reason is too short to record a decision" % field


def test_an_unread_card_field_cannot_change_anything_the_router_answers() -> None:
    """The register's claim, per field, from the shipped router.

    Each pair is two operator-writable cards differing in one key.  If any pair
    ever answers differently, that field has a reader and its register entry
    must be retired in the same commit.
    """
    assert set(_UNREAD_REGISTER) <= set(_MUTATIONS), (
        "the register lists %s, which has no tested value pair, so its 'unread' "
        "is an assertion this file cannot check"
        % sorted(set(_UNREAD_REGISTER) - set(_MUTATIONS))
    )
    for field in sorted(_UNREAD_REGISTER):
        first, second = _MUTATIONS[field]
        assert _answer(field, first) == _answer(field, second), (
            "%s changed the router's answer: the two cards differing only in %s= "
            "gave different routes/costs/wiring, so a reader exists and 'unread' "
            "is no longer the truth" % (field, field)
        )


def test_the_probe_has_power_a_read_field_does_change_the_answer() -> None:
    """The same pairs for the fields that are read.

    Without this, the case above would be a tautology: a probe that showed
    nothing moving anywhere makes "these five do nothing" indistinguishable from
    "this probe cannot see anything".
    """
    for field in sorted(_MUTATIONS):
        if field in _UNREAD_REGISTER:
            continue
        first, second = _MUTATIONS[field]
        assert _answer(field, first) != _answer(field, second), (
            "%s is supposed to reach a reader, yet the router answered both cards "
            "the same - the reader this file counts has stopped mattering" % field
        )
    assert _name_read_by_the_refusal(), (
        "the unknown-provider refusal prints the registry key, not entry.name, "
        "so `name` has no reader either and belongs in the register"
    )


def test_the_census_sees_reads_and_refuses_to_be_blind() -> None:
    """A walk that quietly reads nothing is how a register outlives its subject.

    Three clauses, each failing its own way: the fixtures prove the walk
    recognises all three card-holding spellings and does not credit a
    same-named field of another class; the live tree must show no dynamic card
    access, because ``getattr(card, name)`` is invisible to the walk; and every
    field the behaviour proves is consulted must have at least one lexical
    reader - the clause that reddens if the holder vocabulary is renamed.
    """
    expected_positive = {"max_tokens", "tier", "supports_tools", "supports_vision"}
    seen_positive = _fixture_reads(_POSITIVE_FIXTURE)
    assert seen_positive == expected_positive, (
        "the walk read %s out of a fixture holding %s - a holder spelling it "
        "misses turns every count in this file into a floor of zero"
        % (sorted(seen_positive), sorted(expected_positive))
    )
    assert _fixture_reads(_NEGATIVE_FIXTURE) == set(), (
        "the walk credited a Budget.max_tokens / tier.tier / fallback_models[i].x "
        "read: a name-shape match is not a card read, and substring-matching "
        "`_models` would have made fallback_models a card holder"
    )
    counts, dynamic, files = _census()
    assert files > 10, "the walk saw %d files under minicc/ - it scanned nothing" % files
    assert dynamic == [], (
        "cards are read through getattr/vars/asdict at %s, where the walk cannot "
        "see which field is meant, so the unread register is unverifiable" % dynamic
    )
    blind = sorted(field for field in _behaviour_reads() if counts.get(field, 0) == 0)
    assert blind == [], (
        "the router's answers move with %s, yet the census found no reader - the "
        "walk has gone blind to a real read site (a renamed holder is the usual "
        "cause), and a blind census cannot certify anything unread" % blind
    )
