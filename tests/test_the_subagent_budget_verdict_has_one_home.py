"""M8-T514 — 子代理预算耗尽判词：M8-T500 家族里唯一没有家的成员

M8-T500 给子代理的四种结局各立了消息家（取消、预算 output、超时、命
名失败），但「预算耗尽」这条判词本身漏了：它的两个读者——lifecycle 事
件（审计 sink 读）和 ToolResult summary（父模型读）——各自手拼
`f"子代理预算耗尽：{description}"`。措词漂移时审计日志和模型读到的就不
是同一条事实，没有任何测试会红。

家安在 `minicc/agent/subagent.py`，紧挨家族其他成员。summary 的括号补
语（`（{exc}）`）留在调用方拼装——和 `subagent_failed_message` 的组成
方式一致，差异可见而不是隐式。
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/agent/subagent.py"
SENTENCE = "子代理预算耗尽："


def test_the_home_pins_the_sentence() -> None:
    from minicc.agent.subagent import subagent_budget_exhausted_message

    assert subagent_budget_exhausted_message("调研") == "子代理预算耗尽：调研"


def test_the_sentence_is_spelled_exactly_once() -> None:
    """f-string templates reduce to their literal skeleton before matching.

    The criterion is *starts-with*, not equality: the summary reader's
    template carries a trailing parenthetical skeleton, so an equality
    census would miss a hand-spelled copy there - which is exactly how a
    first draft of this gate let one survive.
    """
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        inside_fstring: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                for child in ast.iter_child_nodes(node):
                    inside_fstring.add(id(child))
        for node in ast.walk(tree):
            if id(node) in inside_fstring:
                continue
            if isinstance(node, ast.JoinedStr):
                skeleton = "".join(
                    part.value
                    for part in node.values
                    if isinstance(part, ast.Constant) and isinstance(part.value, str)
                )
                if skeleton.startswith(SENTENCE):
                    offenders.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}")
            elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and node.value.startswith(SENTENCE)):
                offenders.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the budget-exhausted sentence is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )


class _ClosingProvider:
    def __init__(self) -> None:
        self.closed = False

    async def chat(self, messages, tools, on_delta=None):
        from minicc.llm.base import LLMResponse

        return LLMResponse(content="结论")

    async def close(self) -> None:
        self.closed = True


def _spec(workspace: Path, provider, **overrides):
    from minicc.tools import build_registry
    from minicc.tools.editor import Editor

    from minicc.agent.subagent import build_task_tool_spec

    return build_task_tool_spec(
        provider_factory=lambda: provider,
        workspace=workspace,
        system_prompt="你是 minicc 测试系统提示。",
        base_registry=build_registry(Editor(workspace)),
        **overrides,
    )


def _run(spec, description: str = "调研项目结构"):
    return spec.handler(
        {"description": description, "prompt": "读取 README.md 并总结。"}
    )


def test_both_readers_emit_the_homes_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import minicc.agent.subagent as sa
    from minicc.agent.state import BudgetExceeded

    async def _over_budget(*args, budget=None, **kwargs):
        raise BudgetExceeded("模拟预算耗尽")

    monkeypatch.setattr(sa, "run_agent", _over_budget)
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    events: list[dict] = []
    spec = _spec(tmp_path, _ClosingProvider(), on_trace=events.append)
    result = _run(spec, description="超预算的调研")

    assert result.status == "error" and result.data.get("budget_exceeded") is True
    # The parent model reads the sentence plus the parenthetical exception.
    assert result.summary == "[BUDGET] 子代理预算耗尽：超预算的调研（模拟预算耗尽）", (
        result.summary
    )
    # The audit sink reads the base sentence - no parenthetical.
    assert any(
        event.get("summary") == "子代理预算耗尽：超预算的调研" for event in events
    ), events
