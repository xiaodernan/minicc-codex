"""M8-T135: ``config.json``'s ``stage_routing`` has to reach the router, and the
shapes that used to crash or lie inside it have to be refused at the boundary.

Three claims, one per section:

1. Reachability.  ``minicc/agent/router.py`` documents its knobs as
   ``config.json``'s ``stage_routing`` object and ``minicc/web.py`` asks the
   config for exactly that name through ``getattr(config, "stage_routing",
   None)``.  Nothing declared or read the key, so the default won forever and
   the resolver even reported the documented object as an unread key.  The cases
   here load a real config file and route through a router built with web.py's
   own keyword list.
2. The vocabularies are mirrors.  ``config.py`` cannot import ``minicc.agent``
   (the agent package imports config), so every name list it validates against
   is a copy.  Each copy is pinned here against the consumer - in both
   directions - so a drift is a red gate instead of a config that refuses a
   working knob or accepts a dead one.
3. Refusal, not repair.  Every malformed shape the resolver refuses was first
   fed to the bare router and classified by what it did: an exception escaping
   ``StageRouter`` on the request path, or a plausible route nobody asked for.
   Section 3 carries both tables, so the boundary's claim is exactly as wide as
   what was measured and each refusal names the failure it replaced.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from typing import Any

import pytest

from minicc import config as config_module
from minicc.agent import router as router_module
from minicc.agent.router import ModelTier, StageRouter
from minicc.config import (
    _COST_COLUMNS,
    _CUSTOM_MODEL_KEYS,
    _FAILOVER_KEYS,
    _STAGE_ROUTING_KEYS,
    REASONING_EFFORTS,
    STAGE_NAMES,
    STAGE_TIER_NAMES,
    Config,
    ConfigError,
    load_config,
    normalize_stage_routing,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
ROUTER_SOURCE = REPO_ROOT / "minicc" / "agent" / "router.py"
WEB_SOURCE = REPO_ROOT / "minicc" / "web.py"
MAIN_SOURCE = REPO_ROOT / "minicc" / "main.py"
STAGES = ("inspect", "planning", "implement", "verify", "repair", "review")

# The example from the router's own docstring, kept here as the artifact a user
# would actually copy.  Section 2 proves it still parses out of that docstring.
DOCUMENTED_EXAMPLE: dict[str, Any] = {
    "enabled": True,
    "tiers": {
        "fast": ["gpt-4o-mini", "claude-3-haiku"],
        "balanced": ["gpt-4o", "claude-3.5-sonnet"],
        "reasoning": ["o1", "claude-3.7-sonnet"],
    },
    "stage_map": {
        "planning": "balanced",
        "inspect": "fast",
        "implement": "balanced",
        "verify": "fast",
        "repair": "reasoning",
        "review": "balanced",
    },
    "cost_limits_usd": {
        "planning": 0.05,
        "implement": 0.50,
        "verify": 0.10,
        "repair": 1.00,
    },
    "failover": {"fallback_tiers": ["balanced", "fast"]},
}


@pytest.fixture()
def stage_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.chdir(tmp_path)
    for key in [k for k in os.environ if k.startswith("MINICC_")]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MINICC_HOME", str(home))
    monkeypatch.setenv("MINICC_API_KEY", "sk-gate-key")
    monkeypatch.setenv("MINICC_BASE_URL", "https://gateway.test/v1")
    monkeypatch.setenv("MINICC_MODEL", "gate-model")
    return home


def _load(home: Path, payload: dict[str, Any]) -> Config:
    (home / "config.json").write_text(json.dumps(payload), encoding="utf-8")
    return load_config(workspace=home.parent)


def _route_as_web_does(config: Config, stage: str):
    """Build the router the way ``minicc/web.py`` does, then route one stage."""
    router = StageRouter(
        str(config.model),
        float(config.timeout),
        fallback_models=tuple(getattr(config, "fallback_models", ()) or ()),
        stage_routing_config=getattr(config, "stage_routing", None),
    )
    return router, router.route(stage)


def _bare_router(payload: Any) -> StageRouter:
    """A router fed the raw config, with the resolver taken out of the way.

    ``route()`` short-circuits to the legacy path unless ``enabled`` is truthy, so
    a shape whose payload does not mention the switch has to be measured with it
    on - otherwise the witness reports "nothing happened" for a config that never
    reached the branch under test.  Non-objects go through untouched: their
    measured failure is exactly that they are not a dict.
    """
    value = payload
    if isinstance(payload, dict) and "enabled" not in payload:
        value = {**payload, "enabled": True}
    return StageRouter("gate-model", 180.0, stage_routing_config=value)


def _raw(label: str) -> Any:
    """The unvalidated value of one ``REFUSALS`` row, as the router would receive it."""
    return REFUSALS[label][0]["stage_routing"]


# --- 1. reachability ---------------------------------------------------------------


def test_the_loaded_config_object_reaches_the_router(stage_home: Path) -> None:
    """The defect: this exact file used to produce an empty config and a warning."""
    config = _load(stage_home, {"stage_routing": DOCUMENTED_EXAMPLE})
    assert config.stage_routing == normalize_stage_routing(DOCUMENTED_EXAMPLE), (
        "config.json 的 stage_routing 没有原样到达 Config，字段=%r" % (config.stage_routing,)
    )
    assert config.unrecognized_config_keys == (), (
        "文档里的键仍被报告为「不会被读取」，说明解析器没有咨询它：%r"
        % (config.unrecognized_config_keys,)
    )
    router, route = _route_as_web_does(config, "planning")
    assert router.stage_routing_config == config.stage_routing, (
        "按 web.py 的关键字表构造路由器之后，它拿到的配置对象不是解析器给的那一份"
    )
    assert route.model != config.model, (
        "阶段路由没有生效：planning 仍然用配置的默认模型 %r" % (config.model,)
    )
    assert route.model == "gpt-4o", (
        "planning 按 stage_map 走 balanced 档，档位首模型应是 gpt-4o，实测 %r" % (route.model,)
    )
    assert route.max_cost_usd == 0.05, (
        "cost_limits_usd.planning 没有进到路由里，实测 %r" % (route.max_cost_usd,)
    )


def test_without_the_key_every_stage_keeps_the_configured_model(stage_home: Path) -> None:
    """Control: the fix must not change a deployment that never wrote the knob."""
    config = _load(stage_home, {})
    assert config.stage_routing is None, (
        "没有写 stage_routing 时字段必须是 None（路由器把 None 当作关闭），实测 %r" % (config.stage_routing,)
    )
    _, route = _route_as_web_does(config, "planning")
    assert route.model == "gate-model", (
        "空配置下 planning 必须仍用配置的默认模型，实测 %r" % (route.model,)
    )
    assert route.max_cost_usd is None and route.max_turns is None, (
        "空配置不该产生成本上限或轮次上限：%r / %r" % (route.max_cost_usd, route.max_turns)
    )


def test_both_documented_spellings_and_the_environment_layer_parse_equal(
    stage_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """config.json accepts the object; the environment only carries strings."""
    as_object = _load(stage_home, {"stage_routing": DOCUMENTED_EXAMPLE})
    as_env_spelling = _load(stage_home, {"MINICC_STAGE_ROUTING": DOCUMENTED_EXAMPLE})
    monkeypatch.setenv("MINICC_STAGE_ROUTING", json.dumps(DOCUMENTED_EXAMPLE))
    as_environment = _load(stage_home, {})
    assert as_object.stage_routing == as_env_spelling.stage_routing != {}, (
        "裸键与 MINICC_ 拼法解析出的阶段路由不同或都为空：%r / %r"
        % (as_object.stage_routing, as_env_spelling.stage_routing)
    )
    assert as_environment.stage_routing == as_object.stage_routing, (
        "环境变量里的 JSON 字符串没有还原成同一个对象：%r" % (as_environment.stage_routing,)
    )
    assert as_environment == as_object, (
        "同一个阶段路由从两个配置层读出来，其余字段却不同（precedence 被改坏了）"
    )


def test_every_production_construction_site_is_the_one_this_test_copies(tmp_path: Path) -> None:
    """``_route_as_web_does`` hand-copies the production call; pin it to the originals.

    Two surfaces build the router today - ``web.py`` and, since M11-T7, ``main.py``.  A
    keyword list that changed under this case would leave the reachability test proving
    a composition nobody runs, and the refusal layer guarding one surface while the
    other still hands the router whatever config.json contained.
    """
    expected = ["fallback_models", "stage_routing_config"]
    for source in (WEB_SOURCE, MAIN_SOURCE):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        sites = [
            sorted(keyword.arg for keyword in node.keywords if keyword.arg)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "StageRouter"
        ]
        assert sites == [expected], (
            "%s 构造 StageRouter 的关键字表变了，本文件的「按生产形状路由」用例就不再是那条路径：%r"
            % (source, sites)
        )


# --- 2. the vocabularies are mirrors of the consumer --------------------------------


def _router_reads() -> tuple[set[str], set[str]]:
    """(top-level keys, keys read out of the ``failover`` sub-object).

    Structural, not a substring scan: the receiver is compared against the exact
    expression ``self.stage_routing_config`` (and its ``failover`` indexing), so a
    new nesting level cannot be mistaken for a top-level knob.  The nested test is
    built from the AST rather than by comparing unparsed text, because
    ``ast.unparse`` re-quotes string constants and a hand-written ``"failover"``
    would silently never match.
    """
    tree = ast.parse(ROUTER_SOURCE.read_text(encoding="utf-8"), filename=str(ROUTER_SOURCE))
    top = "self.stage_routing_config"
    read: set[str] = set()
    failover: set[str] = set()
    for node in ast.walk(tree):
        if (
            not isinstance(node, ast.Call)
            or not isinstance(node.func, ast.Attribute)
            or node.func.attr != "get"
            or not node.args
            or not isinstance(node.args[0], ast.Constant)
            or not isinstance(node.args[0].value, str)
        ):
            continue
        receiver = node.func.value
        if ast.unparse(receiver) == top:
            read.add(node.args[0].value)
            continue
        inner = receiver
        if (
            isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Attribute)
            and inner.func.attr == "get"
            and inner.args
            and isinstance(inner.args[0], ast.Constant)
            and inner.args[0].value == "failover"
            and ast.unparse(inner.func.value) == top
        ):
            failover.add(node.args[0].value)
    return read, failover


def _router_custom_model_call() -> ast.Call:
    """The one ``ModelConfig(...)`` construction inside ``_register_custom_models``.

    Bound to that function on purpose: ``router.py`` has several other
    ``ModelConfig`` calls for the built-in catalogue, and copying a knob name list
    from whichever call ``ast.walk`` happens to reach last would pin the wrong
    declaration.
    """
    tree = ast.parse(ROUTER_SOURCE.read_text(encoding="utf-8"), filename=str(ROUTER_SOURCE))
    body = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_register_custom_models"
        ),
        None,
    )
    assert body is not None, "router.py 里找不到 _register_custom_models，镜像无从对照"
    calls = [
        node
        for node in ast.walk(body)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "ModelConfig"
    ]
    assert len(calls) == 1, (
        "_register_custom_models 构造了 %d 个 ModelConfig，这份镜像该对哪一个？" % (len(calls),)
    )
    return calls[0]


def test_the_recognised_key_mirror_equals_what_the_router_indexes() -> None:
    read, failover_keys = _router_reads()
    assert read and failover_keys, (
        "扫描没读到任何键（read=%r failover=%r），等式在空集上没有意义" % (read, failover_keys)
    )
    assert read == set(_STAGE_ROUTING_KEYS), (
        "路由器实际索引的键与校验器认识的名单不等：路由器多读 %s，校验器多认 %s"
        % (sorted(read - set(_STAGE_ROUTING_KEYS)), sorted(set(_STAGE_ROUTING_KEYS) - read))
    )
    assert failover_keys == set(_FAILOVER_KEYS), (
        "failover 下真正有读者的子键是 %s，校验器却按 %s 拒绝"
        % (sorted(failover_keys), sorted(_FAILOVER_KEYS))
    )


def test_the_custom_model_field_mirror_equals_the_routers_own_list() -> None:
    """``custom_models`` entries are fed straight into ``ModelConfig(...)``.

    Split by role, not by hand: one field is the mapping key itself, and only the
    fields that come out of the entry object are things a user writes - so the
    mirror has to equal that second set.  Partitioning by ``name=name`` keeps the
    claim derived from the source instead of from an exception I typed.
    """
    call = _router_custom_model_call()
    keyed = {
        keyword.arg
        for keyword in call.keywords
        if keyword.arg and ast.unparse(keyword.value) == "name"
    }
    from_entry = {keyword.arg for keyword in call.keywords if keyword.arg} - keyed
    assert keyed == {"name"}, (
        "custom_models 的条目里「名字从哪来」的形状变了（实测 %s），这份镜像的分区不再成立"
        % (sorted(keyed),)
    )
    assert from_entry and "cost_usd_per_1m" in from_entry, (
        "没有从 _register_custom_models 读到条目字段名单（%r），等式无法失败"
        % (sorted(from_entry),)
    )
    assert from_entry == set(_CUSTOM_MODEL_KEYS), (
        "ModelConfig 的字段与 custom_models 认识的名单不等：路由器多要 %s，校验器多认 %s"
        % (
            sorted(from_entry - set(_CUSTOM_MODEL_KEYS)),
            sorted(set(_CUSTOM_MODEL_KEYS) - from_entry),
        )
    )
    unpacks = [
        len(node.targets[0].elts)
        for node in ast.walk(ast.parse(ROUTER_SOURCE.read_text(encoding="utf-8")))
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Tuple)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "cost_usd_per_1m"
    ]
    assert unpacks and set(unpacks) == {_COST_COLUMNS}, (
        "成本按 %d 列解包，实测 router.py 里的解包长度是 %s" % (_COST_COLUMNS, sorted(set(unpacks)))
    )


def _dict_keys_named(tree: ast.AST, names: set[str]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in names
            and isinstance(node.value, ast.Dict)
        ):
            keys = [
                key.value
                for key in node.value.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            ]
            found.setdefault(node.targets[0].id, []).extend(keys)
    return found


def test_the_stage_and_tier_wordlists_are_the_routers_own() -> None:
    """Both mirrors also pin the router's three hand-copied stage lists together."""
    tree = ast.parse(ROUTER_SOURCE.read_text(encoding="utf-8"), filename=str(ROUTER_SOURCE))
    stage_copies = _dict_keys_named(tree, {"factors", "default_map"})
    tier_copies = _dict_keys_named(tree, {"defaults"})
    assert set(stage_copies) == {"factors", "default_map"}, (
        "阶段名单的副本形状变了，这个等式就不在检查那三处抄写：%r" % (sorted(stage_copies),)
    )
    assert {frozenset(keys) for keys in stage_copies.values()} == {STAGE_NAMES}, (
        "路由器自己的阶段名单不一致，或与 config 的镜像不等：%r" % (stage_copies,)
    )
    assert set(tier_copies) == {"defaults"} and frozenset(tier_copies["defaults"]) == STAGE_TIER_NAMES, (
        "档位名单（_select_model_for_tier 的 defaults）与 config 的镜像不等：%r" % (tier_copies,)
    )
    assert STAGE_TIER_NAMES == {tier.value for tier in ModelTier}, (
        "档位镜像与 ModelTier 枚举不等：%s vs %s"
        % (sorted(STAGE_TIER_NAMES), sorted(tier.value for tier in ModelTier))
    )
    assert len(STAGE_NAMES) >= 3 and len(STAGE_TIER_NAMES) >= 2, (
        "词表退化到空：%d 个阶段 / %d 个档位，上面的等式会在空集上成立"
        % (len(STAGE_NAMES), len(STAGE_TIER_NAMES))
    )


def test_the_documented_example_is_accepted_by_the_validator() -> None:
    """The router's docstring and the resolver must not drift apart.

    This is what made the knob untrustworthy in the first place: the docstring
    advertised ``failover.enabled`` and ``failover.max_retries_per_model``, which
    nothing read.
    """
    tree = ast.parse(ROUTER_SOURCE.read_text(encoding="utf-8"), filename=str(ROUTER_SOURCE))
    docstring = next(
        (
            ast.get_docstring(node) or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "StageRouter"
        ),
        "",
    )
    assert docstring, "没有读到 StageRouter 的 docstring，等式无从失败"
    start = docstring.index("{")
    example, _end = json.JSONDecoder().raw_decode(docstring[start:])
    assert isinstance(example, dict) and "stage_routing" in example, (
        'docstring 里的例子不再是 {"stage_routing": {...} } 的形状：%r' % (example,)
    )
    documented = example["stage_routing"]
    assert normalize_stage_routing(documented, path="docstring 例子") == documented, (
        "docstring 的例子过不了自己的校验器（文档承诺了一个被拒绝的键）：%r" % (documented,)
    )
    assert documented == DOCUMENTED_EXAMPLE, (
        "本文件顶部那份「用户会照抄的例子」与 docstring 里的不再是同一份：%r" % (documented,)
    )


def test_the_scanned_router_is_the_imported_one() -> None:
    """Every case above parses ``ROUTER_SOURCE``; make sure it is the live module."""
    assert Path(router_module.__file__).resolve() == ROUTER_SOURCE.resolve(), (
        "扫描的 router.py（%s）与解释器加载的模块（%s）不是同一份文件"
        % (ROUTER_SOURCE, router_module.__file__)
    )
    assert Path(config_module.__file__).resolve() == (REPO_ROOT / "minicc" / "config.py").resolve(), (
        "导入的 minicc.config 不是这个仓库里的那一份（%s）" % (config_module.__file__,)
    )


# --- 3. the boundary refuses the measured shapes -----------------------------------

REFUSALS: dict[str, tuple[dict[str, Any], str]] = {
    "top level is a string": ({"stage_routing": "nonsense"}, "stage_routing"),
    "enabled is a string": (
        {"stage_routing": {"enabled": "false"}},
        "stage_routing.enabled",
    ),
    "tiers is not an object": (
        {"stage_routing": {"enabled": True, "tiers": "gpt-4o"}},
        "stage_routing.tiers",
    ),
    "a tier's models are a string": (
        {"stage_routing": {"enabled": True, "tiers": {"fast": "gpt-4o-mini"}}},
        "stage_routing.tiers.fast",
    ),
    "a tier's model list is empty": (
        {"stage_routing": {"enabled": True, "tiers": {"fast": []}}},
        "stage_routing.tiers.fast",
    ),
    # The listed model is one the router would never serve for planning, so the
    # measured fallback is visibly not what this config asked for.
    "an unknown tier key": (
        {"stage_routing": {"tiers": {"turbo": ["o1"]}}},
        "stage_routing.tiers",
    ),
    "a misspelt stage": (
        {"stage_routing": {"stage_map": {"planing": "fast"}}},
        "stage_routing.stage_map",
    ),
    "a stage mapped to no tier": (
        {"stage_routing": {"stage_map": {"planning": "ultra"}}},
        "stage_routing.stage_map.planning",
    ),
    "a cost limit is a string": (
        {"stage_routing": {"cost_limits_usd": {"planning": "0.05"}}},
        "stage_routing.cost_limits_usd.planning",
    ),
    "a cost limit is negative": (
        {"stage_routing": {"cost_limits_usd": {"planning": -1}}},
        "stage_routing.cost_limits_usd.planning",
    ),
    "a turn cap is a string": (
        {"stage_routing": {"max_turns": {"planning": "4"}}},
        "stage_routing.max_turns.planning",
    ),
    "a turn cap is fractional": (
        {"stage_routing": {"max_turns": {"planning": 4.5}}},
        "stage_routing.max_turns.planning",
    ),
    # ``_get_reasoning_effort`` consults this sub-object only for a stage whose
    # tier is ``reasoning``, so the typo is written on ``repair``: that is the
    # spelling that actually reaches a provider request.
    "an effort name is a typo": (
        {"stage_routing": {"reasoning_effort": {"repair": "mediym"}}},
        "stage_routing.reasoning_effort.repair",
    ),
    "failover carries an unread sub-key": (
        {"stage_routing": {"failover": {"enabled": True, "max_retries_per_model": 1}}},
        "stage_routing.failover",
    ),
    "a fallback tier does not exist": (
        {"stage_routing": {"failover": {"fallback_tiers": ["ultra"]}}},
        "stage_routing.failover.fallback_tiers",
    ),
    "an unknown routing key": (
        {"stage_routing": {"zz_typo": 1}},
        "stage_routing",
    ),
    "a custom model entry is a string": (
        {"stage_routing": {"custom_models": {"m": "fast"}}},
        "stage_routing.custom_models.m",
    ),
    "a custom model tier is unknown": (
        {"stage_routing": {"custom_models": {"m": {"tier": "turbo"}}}},
        "stage_routing.custom_models.m.tier",
    ),
    "a custom cost row has the wrong length": (
        {"stage_routing": {"custom_models": {"m": {"cost_usd_per_1m": [1, 2, 3]}}}},
        "stage_routing.custom_models.m.cost_usd_per_1m",
    ),
}

#: rows whose raw value raises out of ``StageRouter`` -> (site, exception measured)
CRASHERS = {
    "top level is a string": ("init", AttributeError),
    "tiers is not an object": ("route", AttributeError),
    "a custom model entry is a string": ("init", AttributeError),
    "a custom model tier is unknown": ("init", ValueError),
    "a stage mapped to no tier": ("route", ValueError),
}

#: rows whose raw value yields a route -> (stage, attribute, measured wrong value)
SILENT_LIES = {
    "enabled is a string": ("planning", "model", "gpt-4o"),
    "a tier's models are a string": ("inspect", "model", "gate-model"),
    "a tier's model list is empty": ("inspect", "model", "gpt-4o-mini"),
    "an unknown tier key": ("planning", "model", "gpt-4o"),
    "a misspelt stage": ("planning", "model", "gpt-4o"),
    "a cost limit is a string": ("planning", "max_cost_usd", "0.05"),
    "a cost limit is negative": ("planning", "max_cost_usd", -1),
    "a turn cap is a string": ("planning", "max_turns", "4"),
    "a turn cap is fractional": ("planning", "max_turns", 4.5),
    "an effort name is a typo": ("repair", "reasoning_effort", "mediym"),
    "a fallback tier does not exist": ("planning", "fallback_models", ()),
}

#: rows whose raw value changes no route at all, measured stage by stage
INERT_ROWS = {
    "failover carries an unread sub-key": (
        {
            "enabled": True,
            "tiers": {"fast": ["gpt-4o-mini"]},
            "failover": {"enabled": True, "max_retries_per_model": 1, "fallback_tiers": ["fast"]},
        },
        {
            "enabled": True,
            "tiers": {"fast": ["gpt-4o-mini"]},
            "failover": {"fallback_tiers": ["fast"]},
        },
    ),
    "an unknown routing key": (
        {"enabled": True, "zz_typo": 1},
        {"enabled": True},
    ),
}

#: the row the router accepts and only pays for at the first bill
DEFERRED_ROW = "a custom cost row has the wrong length"


def test_every_refused_row_is_classified_on_the_router_side() -> None:
    """The four router-side groups must cover ``REFUSALS`` exactly once.

    Without this, adding a refusal row and forgetting its witness would leave the
    table quietly incomplete - the case above would still be green and the new
    row's justification would be prose.
    """
    grouped = list(CRASHERS) + list(SILENT_LIES) + list(INERT_ROWS) + [DEFERRED_ROW]
    assert sorted(grouped) == sorted(REFUSALS), (
        "拒绝表与路由器侧的分类不再是一一对应：多出的 %s，缺的 %s"
        % (
            sorted(set(grouped) - set(REFUSALS)),
            sorted(set(REFUSALS) - set(grouped)),
        )
    )
    assert len(set(grouped)) == len(grouped), "同一行被分到两个类别里，上面的等式就数不出重复"
    assert CRASHERS and SILENT_LIES and INERT_ROWS, (
        "某个类别空了：崩溃 %d / 说谎 %d / 无效 %d，等式会在退化的人群上成立"
        % (len(CRASHERS), len(SILENT_LIES), len(INERT_ROWS))
    )


@pytest.mark.parametrize("label", sorted(REFUSALS))
def test_a_measured_malformation_is_refused_naming_its_path(
    stage_home: Path, label: str
) -> None:
    payload, path = REFUSALS[label]
    with pytest.raises(ConfigError) as refused:
        _load(stage_home, payload)
    message = str(refused.value)
    assert path in message, (
        "拒绝没有点名出错的路径 %r（%s），实测报错：%s" % (path, label, message)
    )
    assert "stage_routing" in message, (
        "拒绝没有说明是哪个配置键（%s），实测报错：%s" % (label, message)
    )


def test_a_bad_environment_value_is_reported_as_a_config_error(
    stage_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MINICC_STAGE_ROUTING", "{not json")
    with pytest.raises(ConfigError) as refused:
        _load(stage_home, {})
    assert "MINICC_STAGE_ROUTING" in str(refused.value), (
        "环境层里的坏 JSON 必须点名那个键，而不是抛 JSONDecodeError：%s" % (refused.value,)
    )


@pytest.mark.parametrize("label", sorted(CRASHERS))
def test_the_crasher_rows_really_escape_the_unvalidated_router(label: str) -> None:
    """For these rows the resolver stands in front of an exception, not a preference.

    ``web.py`` calls ``route()`` outside any ``try``, so the escaped exception is
    what a user would see on the request path.
    """
    site, measured = CRASHERS[label]
    payload = _raw(label)
    with pytest.raises(measured) as escaped:
        if site == "init":
            _bare_router(payload)
        else:
            _bare_router(payload).route("planning")
    assert type(escaped.value) is measured, (
        "%s 实测抛的是 %s，表里记的是 %s——按实测改表，别改断言"
        % (label, type(escaped.value).__name__, measured.__name__)
    )
    with pytest.raises(ConfigError):
        normalize_stage_routing(payload, path="stage_routing")


@pytest.mark.parametrize("label", sorted(SILENT_LIES))
def test_the_silent_rows_really_produce_a_route_nobody_asked_for(label: str) -> None:
    """The other class: no exception, just a number or a model the config did not say.

    Each value below is a measurement of the unvalidated router, so if the router
    is ever fixed this case goes red and the matching refusal can be re-argued -
    it is a witness for the refusal, not a wish about the router.
    """
    stage, attribute, measured = SILENT_LIES[label]
    payload = REFUSALS[label][0]["stage_routing"]
    got = getattr(_bare_router(payload).route(stage), attribute)
    assert got == measured and type(got) is type(measured), (
        "%s：未校验的路由器实测给出 %s.%s=%r（%s），表里记的是 %r（%s）；"
        "两者不一致说明路由行为变了，那条拒绝的理由要重测"
        % (label, stage, attribute, got, type(got).__name__, measured, type(measured).__name__)
    )
    with pytest.raises(ConfigError):
        normalize_stage_routing(payload, path="stage_routing")


def test_the_inert_rows_change_no_route_measured_stage_by_stage() -> None:
    """Two rows are refused because they are dead weight, and that has to be shown.

    A key nothing indexes is exactly the defect this batch is about, so the
    refusal is justified only if the router truly does not move on it.
    """
    for label in sorted(INERT_ROWS):
        with_key, without = INERT_ROWS[label]
        assert label in REFUSALS, "%s 不在拒绝表里，这一类就没有被拒的东西" % label
        left = _bare_router(with_key)
        right = _bare_router(without)
        observed = {
            stage: (
                route.model,
                getattr(route.model_tier, "value", None),
                route.max_cost_usd,
                route.max_turns,
                route.reasoning_effort,
                route.fallback_models,
            )
            for stage, route in ((stage, left.route(stage)) for stage in STAGES)
        }
        baseline = {
            stage: (
                route.model,
                getattr(route.model_tier, "value", None),
                route.max_cost_usd,
                route.max_turns,
                route.reasoning_effort,
                route.fallback_models,
            )
            for stage, route in ((stage, right.route(stage)) for stage in STAGES)
        }
        assert len(observed) == len(STAGES) and observed == baseline, (
            "%s 那两个配置的路由结果不同，说明它并非无效，这一行该重新归类：%r != %r"
            % (label, observed, baseline)
        )
        with pytest.raises(ConfigError):
            normalize_stage_routing(with_key, path="stage_routing")
        normalize_stage_routing(without, path="stage_routing")


def test_a_short_cost_row_is_accepted_and_bites_at_the_first_bill() -> None:
    """The deferred one: construction and routing succeed; pricing does not.

    ``estimate_cost`` unpacks the price tuple positionally, so a three-column row
    is a crash held in reserve until that model is actually routed.
    """
    short = {
        "enabled": True,
        "custom_models": {"m": {"tier": "fast", "cost_usd_per_1m": [1, 2, 3]}},
        "tiers": {"fast": ["m"]},
    }
    assert _bare_router(short).route("inspect").model == "m", (
        "前提变了：三列价格的那一行不再被路由选中，这条见证就没在量它说的东西"
    )
    with pytest.raises(ValueError) as escaped:
        _bare_router(short).estimate_cost("inspect", 1000, 1000)
    assert "unpack" in str(escaped.value), (
        "实测不是解包错（%s），那这条拒绝的理由要重找" % (escaped.value,)
    )
    good = {
        "enabled": True,
        "custom_models": {"m": {"tier": "fast", "cost_usd_per_1m": [1, 2, 3, 0]}},
        "tiers": {"fast": ["m"]},
    }
    assert _bare_router(good).estimate_cost("inspect", 1000, 1000) == pytest.approx(0.003), (
        "四列的控制组算不出 0.003，说明解包列数已经不是这条拒绝的前提了"
    )
    with pytest.raises(ConfigError) as refused:
        normalize_stage_routing(REFUSALS[DEFERRED_ROW][0]["stage_routing"], path="stage_routing")
    assert "cost_usd_per_1m" in str(refused.value), (
        "拒绝没有点名那一列数不对的价格，实测：%s" % (refused.value,)
    )


def test_an_off_switch_written_as_a_string_is_not_an_on_switch() -> None:
    """The Python truthiness trap this refusal exists for, both directions."""
    assert bool("false") is True, "这条见证的前提：非空字符串在 Python 里是真"
    with pytest.raises(ConfigError):
        normalize_stage_routing({"enabled": "false"}, path="stage_routing")
    assert normalize_stage_routing({"enabled": False}, path="stage_routing") == {
        "enabled": False
    }, "真正的 false 必须被接受并原样传下去"
    off = _bare_router({"enabled": False}).route("planning")
    lie = _bare_router({"enabled": "false"}).route("planning")
    empty = _bare_router({"enabled": ""}).route("planning")
    assert (off.model, lie.model, empty.model) == ("gate-model", "gpt-4o", "gate-model"), (
        "开关的三种写法实测不再互相区分（false=%s 「false」=%s 空串=%s），"
        "这条拒绝与其动机脱钩了" % (off.model, lie.model, empty.model)
    )


def test_the_silent_rows_differ_from_the_same_config_spelled_well() -> None:
    """Controls for the silent table: what the user asked for is reachable at all.

    A measured "wrong route" only justifies a refusal if the well-formed spelling
    produces a different one - otherwise both rows measure the same fallback and
    the table pins the router's default rather than the malformation.
    """
    right = _bare_router({"enabled": True, "stage_map": {"planning": "fast"}}).route("planning")
    typo = _bare_router(_raw("a misspelt stage")).route("planning")
    assert (right.model, right.model_tier.value) == ("gpt-4o-mini", "fast"), (
        "拼对的 stage_map 没有把 planning 送进 fast 档（实测 %s/%s），"
        "那「拼错静默走默认」就无从对比" % (right.model, right.model_tier.value)
    )
    assert (typo.model, typo.model_tier.value) == (SILENT_LIES["a misspelt stage"][2], "balanced"), (
        "拼错的 planning 不再走默认档位（实测 %s/%s），表里那条「静默按默认走」得重测"
        % (typo.model, typo.model_tier.value)
    )
    listed = _bare_router({"enabled": True, "tiers": {"fast": ["gpt-4o"]}}).route("inspect")
    assert listed.model == "gpt-4o", (
        "正常写法的档位没有被选中（实测 %r），上面的「字符串档位」对比失效" % (listed.model,)
    )
    for label in ("a tier's models are a string", "a tier's model list is empty"):
        assert _bare_router(_raw(label)).route("inspect").model != listed.model, (
            "%s 与正常写法给出同一个模型，那条静默断言没有量到畸形本身" % label
        )


def test_per_stage_effort_uses_the_global_vocabulary(stage_home: Path) -> None:
    """``medium`` is an alias of a name the provider actually accepts."""
    config = _load(
        stage_home,
        {"stage_routing": {"enabled": True, "reasoning_effort": {"repair": "medium"}}},
    )
    assert config.stage_routing["reasoning_effort"] == {"repair": "mid"}, (
        "档位内的推理名没有走全局同一份归一表：%r" % (config.stage_routing["reasoning_effort"],)
    )
    _, route = _route_as_web_does(config, "repair")
    assert route.reasoning_effort == "mid", (
        "归一后的推理档位没有进到路由：%r" % (route.reasoning_effort,)
    )

    def _effort_of(effort: str) -> str:
        return normalize_stage_routing(
            {"reasoning_effort": {"repair": effort}}, path="stage_routing"
        )["reasoning_effort"]["repair"]

    assert {_effort_of(effort) for effort in REASONING_EFFORTS} == set(REASONING_EFFORTS), (
        "全局词表里的档位没有逐个被阶段版接受：%s"
        % (sorted(set(REASONING_EFFORTS) - {_effort_of(e) for e in REASONING_EFFORTS}),)
    )


def test_reasoning_effort_only_reaches_a_stage_in_the_reasoning_tier() -> None:
    """Pinned limitation of the consumer, measured rather than assumed.

    ``_get_reasoning_effort`` returns the configured name only when the stage's
    tier is ``reasoning``, so an effort on ``planning`` is dropped.  The resolver
    cannot refuse that (``stage_map`` may move planning into the reasoning tier),
    so this records what a user has to know.
    """
    balanced = _bare_router({"enabled": True, "reasoning_effort": {"planning": "high"}})
    moved = _bare_router(
        {
            "enabled": True,
            "stage_map": {"planning": "reasoning"},
            "reasoning_effort": {"planning": "high"},
        }
    )
    assert balanced.route("planning").reasoning_effort is None, (
        "planning 在默认档位（balanced）下竟然带回了推理档：%r，本文件的前提变了"
        % (balanced.route("planning").reasoning_effort,)
    )
    assert moved.route("planning").reasoning_effort == "high", (
        "把 planning 映射到 reasoning 档之后仍拿不到推理档：%r"
        % (moved.route("planning").reasoning_effort,)
    )


def test_a_model_name_the_router_does_not_know_still_falls_back_silently(
    stage_home: Path,
) -> None:
    """Pinned limitation, not a bug this batch fixes.

    Model ids are gateway-defined (``normalize_model_name`` accepts anything
    without control characters), so the resolver cannot refuse an unknown one and
    the router keeps the configured model.  Recorded here so the boundary's claim
    stays exactly as wide as what it checks.
    """
    config = _load(
        stage_home,
        {
            "stage_routing": {
                "enabled": True,
                "tiers": {"fast": ["some-gateway-alias"]},
                "stage_map": {"planning": "fast"},
            }
        },
    )
    _, route = _route_as_web_does(config, "planning")
    assert route.model == "gate-model", (
        "不认识的名字如今被静默换成默认模型；这一条盯的是「行为没变」，实测 %r" % (route.model,)
    )
