"""M6-T1 bounded writable delegation: tiers, depth caps, budgets, concurrency.

These are structural unit tests over ``_SubagentRunner`` — they exercise tool
tier membership, depth-gated recursion, per-child budget wiring, the concurrency
bound, and BudgetExceeded containment without driving a real model turn.
"""

from __future__ import annotations

import types

import pytest

import minicc.agent.subagent as sa
from minicc.agent.loop import Budget
from minicc.agent.state import BudgetExceeded
from minicc.agent.subagent import (
    SUBAGENT_TOOL_NAME,
    _SubagentRunner,
    build_task_tool_spec,
    resolve_subagent_tier,
)
from minicc.tools import Editor, build_registry


def _base(tmp_path):
    return build_registry(Editor(tmp_path))


def _runner(base, tmp_path, **kwargs) -> _SubagentRunner:
    params = dict(
        provider_factory=lambda: None,
        workspace=tmp_path,
        system_prompt="sys",
        base_registry=base,
        max_turns=3,
        timeout_seconds=5,
        cancel_event=None,
    )
    params.update(kwargs)
    return _SubagentRunner(**params)


# --- tier resolution (table-driven) ------------------------------------------

@pytest.mark.parametrize(
    "writable,mode,expected",
    [
        (False, "default", "readonly"),
        (False, "yolo", "readonly"),      # delegation off wins over mode
        (True, "default", "readonly"),    # default can't auto-approve a child write
        (True, "plan", "readonly"),       # plan mode never writes
        (True, "acceptEdits", "write"),
        (True, "yolo", "exec"),
        (True, "bypassPermissions", "exec"),
    ],
)
def test_resolve_tier(writable, mode, expected):
    assert resolve_subagent_tier(writable=writable, permission_mode=mode) == expected


def test_exec_requires_explicit_authorization(tmp_path):
    base = _base(tmp_path)
    write_child = _runner(base, tmp_path, tier="write", permission_mode="acceptEdits")._child_registry().names()
    exec_child = _runner(base, tmp_path, tier="exec", permission_mode="yolo")._child_registry().names()
    assert "write_file" in write_child and "bash" not in write_child
    assert "bash" in exec_child and "write_file" in exec_child
    # No tier ever exposes a network tool to a subagent.
    assert "webfetch" not in exec_child and "web_search" not in exec_child


# --- structural: readonly recon subagent has no task tool --------------------

def test_readonly_subagent_has_no_task_tool(tmp_path):
    base = _base(tmp_path)
    names = _runner(base, tmp_path, tier="readonly")._child_registry().names()
    assert SUBAGENT_TOOL_NAME not in names
    spec = build_task_tool_spec(
        provider_factory=lambda: None, workspace=tmp_path, system_prompt="s", base_registry=base,
    )
    assert spec.risk == "readonly"
    # writable delegation is OFF by default → tier resolves to readonly.
    assert resolve_subagent_tier(writable=False, permission_mode="yolo") == "readonly"


def test_writable_subagent_spec_risk_is_write(tmp_path):
    base = _base(tmp_path)
    spec = build_task_tool_spec(
        provider_factory=lambda: None, workspace=tmp_path, system_prompt="s", base_registry=base,
        writable=True, permission_mode="acceptEdits",
    )
    assert spec.risk == "write"


# --- depth gating: 3rd layer is structurally denied the task tool -----------

def test_depth_two_grandchild_has_no_task_tool(tmp_path):
    base = _base(tmp_path)
    # A depth-0 writable runner spawns a child (depth 1) that MAY carry task.
    depth0_child = _runner(base, tmp_path, depth=0, max_depth=2, tier="write")._child_registry().names()
    assert SUBAGENT_TOOL_NAME in depth0_child
    # A depth-1 runner's child (depth 2) is the last level: no task tool, so a
    # 3rd-level spawn is impossible.
    depth1_child = _runner(base, tmp_path, depth=1, max_depth=2, tier="write")._child_registry().names()
    assert SUBAGENT_TOOL_NAME not in depth1_child


def test_max_depth_one_forbids_all_nesting(tmp_path):
    base = _base(tmp_path)
    names = _runner(base, tmp_path, depth=0, max_depth=1, tier="exec")._child_registry().names()
    assert SUBAGENT_TOOL_NAME not in names


# --- per-child explicit budget wiring ---------------------------------------

def test_child_budget_carries_token_and_soft_limits(tmp_path):
    base = _base(tmp_path)
    runner = _runner(
        base, tmp_path, tier="write",
        max_tokens=1000, soft_max_tokens=400, soft_max_duration_seconds=30.0,
    )
    budget = runner._child_budget()
    assert isinstance(budget, Budget)
    assert budget.max_tokens == 1000 and budget.soft_max_tokens == 400
    assert budget.soft_max_duration_seconds == 30.0 and budget.max_turns == 3


# --- BudgetExceeded is contained: structured failure, parent unaffected -----

def test_budget_exceeded_returns_structured_failure(tmp_path, monkeypatch):
    base = _base(tmp_path)

    async def _raise(*args, **kwargs):
        raise BudgetExceeded("最大 token 预算")

    monkeypatch.setattr(sa, "run_agent", _raise)
    runner = _runner(base, tmp_path, tier="write")
    result = runner._run_bounded("do the thing", "please do the thing carefully")
    assert result.status == "error"
    assert "[BUDGET]" in result.summary
    assert result.data.get("budget_exceeded") is True
    assert "untrusted" in result.security_tags and "subagent" in result.security_tags


# --- results come back tagged untrusted -------------------------------------

def test_successful_subagent_result_is_untrusted(tmp_path, monkeypatch):
    base = _base(tmp_path)

    async def _ok(*args, **kwargs):
        return types.SimpleNamespace(answer="all good", tokens_used={"total_tokens": 7}, turns=1, tool_calls_total=0)

    monkeypatch.setattr(sa, "run_agent", _ok)
    runner = _runner(base, tmp_path, tier="write")
    result = runner._run_bounded("goal here", "a sufficiently long prompt body")
    assert result.status == "ok"
    assert "untrusted" in result.security_tags and "subagent" in result.security_tags
    assert result.data["tokens_used"]["total_tokens"] == 7


# --- concurrency bound rejects the 4th with a readable error, not a hang -----

def test_fourth_concurrent_subagent_is_rejected(tmp_path):
    base = _base(tmp_path)
    runner = _runner(base, tmp_path, tier="readonly")
    held = [sa._SUBAGENT_SLOTS.acquire(timeout=1) for _ in range(sa.MAX_CONCURRENT_SUBAGENTS)]
    assert all(held)
    try:
        with pytest.raises(sa.ToolError):
            runner.run({"description": "one more", "prompt": "push past the concurrency limit"})
    finally:
        for _ in held:
            sa._SUBAGENT_SLOTS.release()
