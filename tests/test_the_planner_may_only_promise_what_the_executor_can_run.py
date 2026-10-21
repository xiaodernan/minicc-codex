"""M8-T340 — 规划器只能承诺执行器跑得动的计划

关于"只读计划能用哪些工具"，仓库里有**四份**手抄的名单：

| 名单 | 内容 |
| --- | --- |
| 提示词（`PLANNER_SYSTEM_PROMPT` 第 3 条） | 7 个：read_file、grep、git_status、git_diff、write_file、edit_file、bash |
| `DEFAULT_ALLOWED_TOOLS`（policy 上限） | 9 个：多出 git_summary、git_merge_precheck |
| `PLANNER_KIND_TOOLS["readonly"/"review"/"merge"]` | 6 个：多出 git_summary、git_merge_precheck |
| `READONLY_DAG_TOOLS`（DAG 执行器的硬边界） | 4 个：read_file、grep、git_status、git_diff |

于是：**规划器认可的计划，执行器会拒绝**。一个只读任务里带 `git_summary` 的
计划过了 `validate_dynamic_plan`（它在 policy 上限里、也在 kind 表里），到了
DAG 那里却被硬拒（越过了 4 个工具的边界）——Web 侧的"提前跳过"检查会把它
退回主 Agent，而事件里给的理由是"动态计划包含非只读节点"：那个计划的节点
**全是只读的**，理由是假的。

本门钉住：只读类的 kind 用的就是执行器那道边界（一个家）；上限里没有"任何
kind 都用不到"的死工具；提示词列的就是校验器收的那一套；行为上，规划器不再
认可执行器会拒的计划。
"""

from __future__ import annotations

import re

import pytest

from minicc.agent.graph import GraphValidationError, READONLY_DAG_TOOLS
from minicc.agent.planner import (
    DEFAULT_ALLOWED_TOOLS,
    PLANNER_KIND_TOOLS,
    PLANNER_KINDS,
    PLANNER_SYSTEM_PROMPT,
    build_plan,
    validate_dynamic_plan,
)


def _prompt_tools() -> set[str]:
    """The tool names the prompt itself offers the model."""
    line = next(
        (row for row in PLANNER_SYSTEM_PROMPT.splitlines() if "只能来自" in row),
        "",
    )
    assert line, "the planner prompt no longer states the allowed tools"
    tail = line.split("：", 1)[-1].strip().rstrip("。")
    return {name.strip() for name in tail.split("、") if name.strip()}


def test_the_readonly_kinds_use_the_executors_own_boundary() -> None:
    """One home: the planner may not promise more than the DAG can run."""
    for kind in ("readonly", "review", "merge"):
        overflow = set(PLANNER_KIND_TOOLS[kind]) - READONLY_DAG_TOOLS
        assert not overflow, (kind, sorted(overflow))


def test_the_ceiling_has_no_dead_entries() -> None:
    """A tool no kind may use is not "allowed" in any sense."""
    union = set().union(*(set(tools) for tools in PLANNER_KIND_TOOLS.values()))
    assert set(DEFAULT_ALLOWED_TOOLS) == union, sorted(
        set(DEFAULT_ALLOWED_TOOLS) ^ union
    )


def test_the_prompt_lists_exactly_what_the_validator_accepts() -> None:
    """The prompt is the model's copy of the same rule."""
    union = set().union(*(set(tools) for tools in PLANNER_KIND_TOOLS.values()))
    assert _prompt_tools() == union, sorted(_prompt_tools() ^ union)


def test_a_plan_the_executor_would_refuse_is_not_accepted() -> None:
    """The behaviour: the planner falls back instead of promising a doomed plan."""
    plan = {
        "name": "readonly-with-summary",
        "tasks": [
            {"id": "inspect", "kind": "readonly", "allowed_tools": ["git_summary"]},
        ],
    }
    with pytest.raises(GraphValidationError):
        validate_dynamic_plan(plan)
    result = build_plan(plan)
    assert result.source == "fixed_fallback", result.source


def test_a_plan_the_executor_can_run_is_still_accepted() -> None:
    """The control: the rule is a boundary, not a blanket ban."""
    plan = {
        "name": "readonly-review",
        "tasks": [
            {"id": "inspect", "kind": "readonly", "allowed_tools": ["read_file", "grep"]},
            {"id": "review", "kind": "review", "depends_on": ["inspect"],
             "allowed_tools": ["git_diff"]},
        ],
    }
    validated = validate_dynamic_plan(plan)
    assert validated.name == "readonly-review"
    for task in validated.tasks:
        assert not set(task.allowed_tools) - READONLY_DAG_TOOLS, task.id


def test_every_kind_has_a_table_and_the_fixed_plan_still_validates() -> None:
    """The control: the tables cover the kinds, and the fallback still works."""
    assert set(PLANNER_KIND_TOOLS) == set(PLANNER_KINDS)
    fallback = build_plan(None, fallback_name="inspect_implement_verify")
    assert fallback.source == "fixed_fallback"
    for task in fallback.plan.tasks:
        assert task.kind in PLANNER_KINDS, task.kind
        assert not set(task.allowed_tools) - set(DEFAULT_ALLOWED_TOOLS), task.id
