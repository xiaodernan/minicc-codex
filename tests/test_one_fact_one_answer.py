"""M8-T308 — 同一件事的两个答案：事件里的风险、日志的说明、以及"被挤掉的真目标"

这一批是读代码读出来的三条，形状各不相同，但都落在同一个主题上：**同一个事实，
被两个地方用不同的口径回答**。

本门禁钉住：

* 同一次调用的**两条授权事件**带的是**同一个**风险；
* 日志的说明与它**实际**做的事一致（更严，且只在一个方向上更严）；
* 失败测试的**函数名**不再当成 token，真目标不会被**误命中挤掉**。
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from minicc.agent.repair import repair_scope
from minicc.logging_setup import redact


# --- M8-T308a: two events about one call carry one risk ----------------------


def test_the_planner_whitelist_denial_uses_the_effective_risk() -> None:
    """The decision event right below it carries the effective one."""
    from minicc import web

    source = inspect.getsource(web.AgentService)
    assert 'node_registry.risk_of(name) or "unknown"' not in source, (
        "the whitelist-denial event still carries the *declared* risk, so "
        "the same call has two risks in two events"
    )
    assert "effective_risk(" in source


# --- M8-T308b: the log's docstring says what it does -------------------------


def test_the_log_docstring_says_it_is_stricter() -> None:
    """It masks every labelled value; the model context does not."""
    doc = inspect.getdoc(redact) or ""
    assert "stricter" in doc, (
        "the log's own docstring does not say that it is deliberately "
        "stricter than the model context - which is the one direction that "
        "is safe, and the direction someone would 'unify' the wrong way"
    )


def test_the_log_is_actually_stricter_than_the_model_context() -> None:
    """The control: the claim is true."""
    from minicc.tools.registry import redact_text

    source = 'self.token = compute()'
    assert redact_text(source)[0] == source, (
        "the model context rewrote ordinary source"
    )
    assert redact(source) != source, (
        "the log left an ordinary source line alone - it is supposed to be "
        "stricter than the model context"
    )


# --- M8-T308c: the real target is not crowded out ----------------------------


def test_the_function_name_does_not_become_a_token() -> None:
    """``test_sum`` describes the behaviour, not the module."""
    scope = repair_scope(
        [
            {"write": True, "path": "src/summary.py"},
            {"write": True, "path": "src/consume.py"},
            {"write": True, "path": "src/ledger/service.py"},
        ],
        {"failed_tests": ["tests/test_ledger.py::test_sum"]},
    )
    assert scope["repair_targets"] == ["src/ledger/service.py"], (
        f"the function name's fragments matched unrelated files: {scope}"
    )


def test_many_weak_matches_do_not_crowd_out_the_real_target() -> None:
    """The cut keeps the last twelve - so the best twelve must be last.

    The real target is written **first**, and the weak matches (the token
    only appears *inside* a segment) come after it - so without a ranking
    the cut drops it.
    """
    writes = [{"write": True, "path": "src/ledger/service.py"}]
    writes.extend(
        {"write": True, "path": f"src/ledgerx/module_{index}.py"}
        for index in range(20)
    )
    scope = repair_scope(writes, {"failed_tests": ["tests/test_ledger.py::test_sum"]})
    assert "src/ledger/service.py" in scope["repair_targets"], (
        f"the real target was crowded out: {scope['repair_targets']}"
    )


def test_a_whole_segment_match_beats_a_substring_match() -> None:
    """The two kinds of match are not equally good."""
    scope = repair_scope(
        [
            {"write": True, "path": "src/ledger/notes.md"},
            {"write": True, "path": "src/ledgerx/service.py"},
            {"write": True, "path": "src/ledger/service.py"},
        ],
        {"failed_tests": ["tests/test_ledger.py::test_sum"]},
    )
    assert scope["repair_targets"][-1] == "src/ledger/service.py", (
        f"the whole-segment match is not ranked first: {scope['repair_targets']}"
    )


def test_an_ordinary_scope_is_unchanged() -> None:
    """The control: the ordinary case is unchanged.

    ``tests/test_app.py`` names ``app``, and ``src/app.py`` is that module
    - so this is a **match**, and the scope says so.
    """
    scope = repair_scope(
        [{"write": True, "path": "src/app.py"}],
        {"failed_tests": ["tests/test_app.py::test_app"]},
    )
    assert scope["reason"] == "matched_failed_test", scope
    assert scope["repair_targets"] == ["src/app.py"], scope
