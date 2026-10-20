"""M8-T291 — 备用模型列表里不能有**这条路由正在用的**那个

故障转移的第一步是"换到备用模型"。如果备用列表的第 0 位就是当前模型，
那"切换"换回同一个模型——**故障转移成了空转**，而事件却写着
"switched to the fallback model"。

原来的修法排掉的是**部署级**默认模型；可开启阶段路由后，这条路由真正用的
是**档位解析出来的**那个模型，两者通常不同——于是主模型仍排在第 0 位。

本门禁钉住：备用列表不含**这条路由的**模型；部署级默认模型仍然排掉。
"""

from __future__ import annotations

from typing import Any

import pytest

from minicc.agent.router import StageRouter

FULL: dict[str, Any] = {
    "enabled": True,
    "tiers": {"balanced": ["gpt-4o", "claude-3.5-sonnet"]},
    "stage_map": {"planning": "balanced"},
    "failover": {"fallback_tiers": ["balanced"]},
}


def test_the_resolved_primary_is_not_offered_as_a_fallback() -> None:
    """The route's own model, not the deployment's default."""
    router = StageRouter("gateway-main", 100.0, stage_routing_config=FULL)
    route = router.route("planning")
    assert route.model == "gpt-4o"
    assert "gpt-4o" not in route.fallback_models, (
        f"the primary is in its own fallback list: {route.fallback_models}"
    )
    assert "claude-3.5-sonnet" in route.fallback_models


def test_the_deployment_default_is_still_excluded() -> None:
    """The control: both are excluded."""
    router = StageRouter("gateway-main", 100.0, stage_routing_config={
        **FULL,
        "tiers": {"balanced": ["gpt-4o", "gateway-main", "claude-3.5-sonnet"]},
    })
    route = router.route("planning")
    assert "gateway-main" not in route.fallback_models, route.fallback_models


def test_a_normal_fallback_list_still_works() -> None:
    """The control: the ordinary case is unchanged.

    The tier resolves to its first model, so that one is the primary and is
    not offered as a fallback; the rest of the tier is.
    """
    router = StageRouter("gpt-4o", 100.0, stage_routing_config={
        "enabled": True,
        "tiers": {"balanced": ["gpt-4.1", "gpt-4o-mini"]},
        "stage_map": {"planning": "balanced"},
        "failover": {"fallback_tiers": ["balanced"]},
    })
    route = router.route("planning")
    assert route.model == "gpt-4.1"
    assert route.fallback_models == ("gpt-4o-mini",)
