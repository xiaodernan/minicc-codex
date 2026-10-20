"""M8-T309 — 指令要跟"实际发生了什么"对得上；门禁不该被无关的排版改动弄红

两条，都是上一批（M8-T300 / M8-T308）留下的尾巴：

* **超时的指令**：验证超时时，完成评估给出的指令是"修复最近一次验证**失败**并
  重新取得通过结果"——而超时**根本没有失败**，它只是没跑完。模型于是被派去修一个
  从来没有失败过的命令。
* **源码文本门禁的窗口**：`test_the_web_face_does_not_recompute_the_write_flag`
  用固定 **2000 字符**的窗口去找那一行。它想问的是"这个函数里有没有携带规范判定"，
  而答案**不该取决于**那一行与标记之间恰好隔了多少文字——于是函数里一处合法的
  改动（多行调用、一段注释）就能把那一行推出窗口，让门禁无故变红。

本门禁钉住这两条。
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from minicc.agent.completion import _enforce_completion_evidence


def _decision(status: str) -> object:
    from minicc.agent.completion import CompletionDecision

    decision = CompletionDecision()
    _enforce_completion_evidence(
        decision,
        verification_results=[{"status": status}],
        events=[],
        allow_changes=True,
    )
    return decision


def test_a_timeout_is_not_told_to_fix_a_failure() -> None:
    """A timeout produced no verdict - the repair is to make it finishable."""
    decision = _decision("timed_out")
    instruction = str(decision.missing[0])
    assert "超时" in instruction, instruction
    assert "验证失败" not in instruction, (
        f"a timeout was reported as a failure to repair: {instruction}"
    )


def test_a_real_failure_still_says_so() -> None:
    """The control: the ordinary case is unchanged."""
    decision = _decision("failed")
    assert "验证失败" in str(decision.missing[0]), decision.missing


def test_a_blocked_check_says_so() -> None:
    """The control: the ordinary case is unchanged."""
    decision = _decision("blocked")
    assert "阻止" in str(decision.missing[0]), decision.missing


def test_the_source_text_gate_reads_the_function_not_a_window() -> None:
    """The question is about the function, not about how far away the line is."""
    path = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "test_five_places_where_one_fact_was_read_differently.py"
    )
    source = path.read_text(encoding="utf-8")
    assert "start + 2000" not in source, (
        "the gate still reads a fixed character window, so an unrelated edit "
        "in that function can make it red for no reason"
    )
    assert "sibling" in source, (
        "the gate should read the function's own extent"
    )


def test_the_gate_still_finds_the_line() -> None:
    """The control: the gate still means what it says."""
    web_source = (
        Path(__file__).resolve().parents[1] / "minicc" / "web.py"
    ).read_text(encoding="utf-8")
    marker = "def on_tool(call: ToolCall, result: ToolResult) -> None:"
    start = web_source.index(marker)
    line_start = web_source.rfind("\n", 0, start) + 1
    indent = web_source[line_start:start]
    rest = web_source[start:]
    sibling = rest.find("\n" + indent + "def ")
    branch = rest if sibling == -1 else rest[:sibling]
    assert '"write": bool(feedback.get("write"))' in branch
