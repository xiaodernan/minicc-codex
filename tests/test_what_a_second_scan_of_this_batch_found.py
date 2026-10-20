"""M8-T291 — 一次扫描抓到的六条：统计口径、排序键、词边界与"同族不同拼写"

这一批做完之后做了一次扫描（逐个文件读 + 实跑复现），报出六条问题：

| 编号 | 位置 | 问题 |
| --- | --- | --- |
| M8-T291a | `bench_compare._pass_at_k` | 可评分但**没有 draws** 的任务被从分母里**剔除**，pass@k 描述的是子集却像全集；那句承诺"没有抽样结果"的提示永远不出现 |
| M8-T291b | `pricing.load_price_table` | 部署用 `MINICC_PRICING_JSON` 覆盖一个**拼写不同、折叠后同族**的模型时，公布价赢了，部署的价格被丢弃 |
| M8-T291c | `impact.analyze_change_impact` | `recommended_tests` 按**字母序**排（兄弟列表 `impacted_files` 按依赖距离排）——截断丢掉的是距离为 1 的测试 |
| M8-T291d | `router.StageRouter._get_fallback_models` | fallback 列表可能含**主模型本身** → 故障转移变成空转，事件却说"切换到了备用模型" |
| M8-T291e | `repair.repair_scope` | 失败测试的分词把 `test`/`tests`/`py` 当通用词，且是**裸子串**匹配 → `attestation.py`、`latest/parser.py` 全被误判为修复目标 |
| M8-T291f | `orchestration._CONNECTOR_RE` | 英文分支**没有词边界** → `understand`/`command`/`handler`/`sandbox` 里的 "and" 全被当连接词 |

This door pins all six.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from minicc.agent.orchestration import _CONNECTOR_RE, assess_complexity
from minicc.agent.repair import repair_scope
from minicc.bench_compare import _pass_at_k
from minicc.pricing import price_for


# --- M8-T291a: pass@k over a subset ------------------------------------------


def test_pass_at_k_is_unavailable_when_a_gradable_row_has_no_draws() -> None:
    """It used to describe a subset while looking like the whole suite."""
    rows = [
        {"task_id": "A", "passed": True, "draws": [True] * 5 + [False] * 5},
        {"task_id": "B", "passed": False, "draws": []},
    ]
    assert _pass_at_k(rows, 10) is None, (
        "pass@k was computed over a subset of the gradable tasks"
    )


def test_pass_at_k_is_available_when_every_row_has_enough_draws() -> None:
    """The control: the ordinary case is unchanged."""
    rows = [
        {"task_id": "A", "passed": True, "draws": [True] * 5 + [False] * 5},
        {"task_id": "B", "passed": False, "draws": [True] * 5 + [False] * 5},
    ]
    value = _pass_at_k(rows, 10)
    assert value is not None
    assert 0.0 <= value <= 1.0


# --- M8-T291b: a deployment's own price wins --------------------------------


def test_a_deployment_override_wins_over_the_published_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The spelling differs from the table's; the fold is the same family."""
    monkeypatch.setenv("MINICC_PRICING_JSON", json.dumps({
        "claude-3.5-sonnet": {"input": 999.0, "output": 999.0},
    }))
    price = price_for("claude-3.5-sonnet")
    assert price is not None
    assert price.input_per_mtok == 999.0, (
        "the deployment's own price was silently ignored"
    )


def test_an_exact_spelling_still_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    """The control: the ordinary spelling."""
    monkeypatch.setenv("MINICC_PRICING_JSON", json.dumps({
        "gpt-4o": {"input": 42.0, "output": 42.0},
    }))
    price = price_for("gpt-4o")
    assert price is not None
    assert price.input_per_mtok == 42.0


# --- M8-T291c: the recommended tests are ordered by distance ----------------


def test_the_recommended_tests_are_ordered_by_dependency_distance(
    tmp_path: Path,
) -> None:
    """The two sibling lists used two different sort keys.

    The chain is built so the **alphabetically first** test is the
    **furthest** one: ``aaa_test`` -> ``zzz_test`` -> ``thing_test`` ->
    ``thing`` (changed).  Distance order keeps ``thing_test`` (distance 1);
    dictionary order would keep ``aaa_test`` (distance 3) and throw the
    close one away.
    """
    from minicc.impact import analyze_change_impact

    package = tmp_path / "pkg"
    (package / "deep").mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "deep" / "__init__.py").write_text("", encoding="utf-8")
    (package / "deep" / "thing.py").write_text("helper = 1\n", encoding="utf-8")
    (package / "thing_test.py").write_text(
        "from pkg.deep.thing import helper\n\ndef test_helper():\n    assert helper\n",
        encoding="utf-8",
    )
    (package / "zzz_test.py").write_text(
        "from pkg.thing_test import test_helper\n\ndef test_wrapped():\n    assert True\n",
        encoding="utf-8",
    )
    (package / "aaa_test.py").write_text(
        "from pkg.zzz_test import test_wrapped\n\ndef test_far():\n    assert True\n",
        encoding="utf-8",
    )

    result = analyze_change_impact(tmp_path, ["pkg/deep/thing.py"], limit=1)
    recommended = [row["path"] for row in result.get("recommended_tests", [])]
    assert recommended, "no test was recommended"
    assert "pkg/thing_test.py" in recommended, (
        f"the alphabetically-first test was kept instead of the close one: {recommended}"
    )


# --- M8-T291d: the fallback list never offers the primary --------------------


def test_the_fallback_list_never_offers_the_primary_model() -> None:
    """Otherwise the first "switch" switches to the same model."""
    from minicc.agent.router import StageRouter

    router = StageRouter("gpt-4o", stage_routing_config={
        "enabled": True,
        "tiers": {"balanced": ["gpt-4o", "gpt-4.1"]},
        "failover": {"fallback_tiers": ["balanced"]},
    })
    fallbacks = router._get_fallback_models("planning")
    assert "gpt-4o" not in fallbacks, (
        f"the primary model is in its own fallback list: {fallbacks}"
    )
    assert "gpt-4.1" in fallbacks


def test_a_normal_fallback_list_still_works() -> None:
    """The control: the ordinary case."""
    from minicc.agent.router import StageRouter

    router = StageRouter("gpt-4o", stage_routing_config={
        "enabled": True,
        "tiers": {"balanced": ["gpt-4.1", "gpt-4o-mini"]},
        "failover": {"fallback_tiers": ["balanced"]},
    })
    assert router._get_fallback_models("planning") == ("gpt-4.1", "gpt-4o-mini")


# --- M8-T291e: the test file's own name says nothing about the code ---------


def test_the_generic_test_words_do_not_make_everything_a_target() -> None:
    """``attestation.py`` merely *contains* "test"."""
    scope = repair_scope(
        [
            {"write": True, "path": "src/attestation.py"},
            {"write": True, "path": "src/latest/parser.py"},
            {"write": True, "path": "docs/protester.md"},
        ],
        {"failed_tests": ["tests/test_ledger.py::test_sum"]},
    )
    assert scope["reason"] == "changed_file_evidence", (
        f"the scope claimed a test match it did not have: {scope}"
    )


def test_the_real_target_is_not_pushed_out_by_false_hits() -> None:
    """The token often names a **directory**, not the file.

    ``tests/test_ledger.py`` refers to ``src/ledger/service.py`` - the token
    is in the directory, so a match against the file's stem alone finds
    nothing and the scope falls back to "every changed file", which is
    the unfocused repair this function exists to prevent.
    """
    scope = repair_scope(
        [
            {"write": True, "path": "src/attestation.py"},
            {"write": True, "path": "src/ledger/service.py"},
        ],
        {"failed_tests": ["tests/test_ledger.py::test_sum"]},
    )
    assert scope["reason"] == "matched_failed_test", scope
    assert scope["repair_targets"] == ["src/ledger/service.py"], scope


# --- M8-T291f: the connector words need word boundaries ---------------------


def test_a_word_merely_containing_and_is_not_a_connector() -> None:
    """``understand``, ``command``, ``handler``, ``sandbox``, ``strengthen``."""
    found = _CONNECTOR_RE.findall(
        "understand the command handler and strengthen the sandbox"
    )
    assert len(found) == 1, f"one connector became {len(found)}: {found}"


def test_a_real_connector_is_still_counted() -> None:
    """The control: the ordinary case."""
    assert _CONNECTOR_RE.search("fix the parser and run the tests")
    assert _CONNECTOR_RE.search("先修好解析器，然后再跑测试")


def test_a_single_goal_request_is_not_fanned_out() -> None:
    """The observable consequence of the false connectors."""
    assessment = assess_complexity(
        "understand the command handler and strengthen the sandbox"
    )
    assert assessment.child_count == 0, (
        f"a single-goal request was fanned out: {assessment}"
    )
    assert assessment.score < assessment.threshold, assessment
