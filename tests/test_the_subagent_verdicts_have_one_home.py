"""M8-T500 — 子代理判词四个家：lifecycle 与 ToolResult 各拼一句

子代理的四种结局（取消、预算终止、超时、命名失败）在 `subagent.py` 里各
有两个读者：lifecycle 事件（审计 sink 读）和 ToolResult 的
summary/output（父模型读）。每条判词被手拼两到四次，共十个家。一处改了
措词其余没跟上，审计日志和模型读到的就是不同的事实——没有任何测试会
红。

家安在 `minicc/agent/subagent.py` 模块层，紧挨 `_bounded_output`——所有
调用点都在这个模块。家只拥有措词：分支的控制流（set cancel、join、返
回哪个 status）留在原地。
"""

from __future__ import annotations

import ast
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/agent/subagent.py"
CANCELLED = "子代理被取消："
BUDGET_OUTPUT = "子代理在其独立预算内未完成，已终止。请缩小委派范围或拆成多步后重试。"
TIMEOUT = "子代理超时（>s）："
FAILED = "子代理失败：（）"
HOMES = {
    "subagent_cancelled_message(": 5,  # 1 definition + 4 call sites
    "subagent_budget_failed_output(": 3,  # 1 definition + 2 call sites
    "subagent_timeout_message(": 3,
    "subagent_failed_message(": 3,
}


def _literal_shapes():
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        inside_fstring: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                for child in ast.iter_child_nodes(node):
                    inside_fstring.add(id(child))
        for node in ast.walk(tree):
            if id(node) in inside_fstring:
                continue
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                yield path, node.lineno, node.value
            elif isinstance(node, ast.JoinedStr):
                parts = [
                    part.value
                    for part in node.values
                    if isinstance(part, ast.Constant) and isinstance(part.value, str)
                ]
                yield path, node.lineno, "".join(parts)


def _sites_of(sentence: str) -> list[str]:
    return [
        f"{path.relative_to(REPO).as_posix()}:{lineno}"
        for path, lineno, text in _literal_shapes()
        if text == sentence
    ]


def _one_home(sentence: str) -> None:
    offenders = _sites_of(sentence)
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        f"the sentence {sentence!r} is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )


# --- the homes pin the sentences ----------------------------------------------


def test_the_cancelled_home_pins_the_sentence() -> None:
    from minicc.agent.subagent import subagent_cancelled_message

    assert subagent_cancelled_message("调研") == "子代理被取消：调研"


def test_the_budget_home_pins_the_sentence() -> None:
    from minicc.agent.subagent import subagent_budget_failed_output

    assert subagent_budget_failed_output() == BUDGET_OUTPUT


def test_the_timeout_home_pins_the_sentence() -> None:
    from minicc.agent.subagent import subagent_timeout_message

    assert subagent_timeout_message(600, "调研") == "子代理超时（>600s）：调研"


def test_the_failed_home_pins_the_sentence() -> None:
    from minicc.agent.subagent import subagent_failed_message

    assert subagent_failed_message("调研", "boom") == "子代理失败：调研（boom）"


# --- census: each sentence is spelled exactly once in the package --------------


def test_the_cancelled_sentence_is_spelled_exactly_once() -> None:
    _one_home(CANCELLED)


def test_the_budget_sentence_is_spelled_exactly_once() -> None:
    _one_home(BUDGET_OUTPUT)


def test_the_timeout_sentence_is_spelled_exactly_once() -> None:
    _one_home(TIMEOUT)


def test_the_failed_sentence_is_spelled_exactly_once() -> None:
    _one_home(FAILED)


def test_every_home_is_asked_by_every_site() -> None:
    source = (REPO / HOME).read_text(encoding="utf-8")
    for name, expected in HOMES.items():
        assert source.count(name) == expected, (
            f"subagent.py asks {name} {source.count(name)} times, "
            f"expected {expected}"
        )


# --- one behavioural assertion per branch -------------------------------------


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


class _ClosingProvider:
    def __init__(self) -> None:
        self.closed = False

    async def chat(self, messages, tools, on_delta=None):
        from minicc.llm.base import LLMResponse

        return LLMResponse(content="结论")

    async def close(self) -> None:
        self.closed = True


def test_the_cancel_flag_branch_emits_the_homes_sentence(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    cancel = threading.Event()
    cancel.set()
    events: list[dict] = []
    spec = _spec(
        tmp_path, _ClosingProvider(), cancel_event=cancel, on_trace=events.append
    )
    result = _run(spec, description="被取消的调研")
    assert result.status == "cancelled"
    assert result.summary == "[CANCELLED] 子代理被取消：被取消的调研", result.summary
    assert any(
        event.get("summary") == "子代理被取消：被取消的调研" for event in events
    ), events


def test_the_agent_cancelled_branch_emits_the_homes_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import minicc.agent.subagent as sa
    from minicc.agent.loop import AgentCancelled

    async def _cancelled(*args, **kwargs):
        raise AgentCancelled("cancelled by the child loop")

    monkeypatch.setattr(sa, "run_agent", _cancelled)
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    events: list[dict] = []
    spec = _spec(tmp_path, _ClosingProvider(), on_trace=events.append)
    result = _run(spec, description="被孩子取消的调研")
    assert result.status == "cancelled"
    assert result.summary == "[CANCELLED] 子代理被取消：被孩子取消的调研", result.summary
    assert any(
        event.get("summary") == "子代理被取消：被孩子取消的调研" for event in events
    ), events


def test_the_budget_branch_emits_the_homes_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import minicc.agent.subagent as sa
    from minicc.agent.state import BudgetExceeded

    async def _over_budget(*args, budget=None, **kwargs):
        raise BudgetExceeded("模拟预算耗尽")

    monkeypatch.setattr(sa, "run_agent", _over_budget)
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    spec = _spec(tmp_path, _ClosingProvider())
    result = _run(spec, description="超预算的调研")
    assert result.status == "error" and result.data.get("budget_exceeded") is True
    assert result.output == BUDGET_OUTPUT, result.output


def test_the_timeout_branch_emits_the_homes_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import minicc.agent.subagent as sa

    calls = [0]

    def fake_monotonic() -> float:
        # First call is the run's ``started``; every later call is far past
        # the deadline, so the wait loop breaks as timed-out immediately.
        # ``execute()`` never calls ``time.monotonic`` itself, so only the
        # main thread drives this counter.
        calls[0] += 1
        return 0.0 if calls[0] == 1 else 1e9

    monkeypatch.setattr(sa, "time", SimpleNamespace(monotonic=fake_monotonic))
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    events: list[dict] = []
    spec = _spec(tmp_path, _ClosingProvider(), on_trace=events.append)
    result = _run(spec, description="超时的调研")
    assert result.status == "timed_out"
    assert result.summary == "[TIMEOUT] 子代理超时（>600s）：超时的调研", result.summary
    assert any(
        event.get("summary") == "子代理超时（>600s）：超时的调研" for event in events
    ), events


def test_the_named_error_branch_emits_the_homes_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import minicc.agent.subagent as sa

    async def _named_error(*args, **kwargs):
        return SimpleNamespace(error="阶段成本上限", tokens_used={"total_tokens": 7})

    monkeypatch.setattr(sa, "run_agent", _named_error)
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    spec = _spec(tmp_path, _ClosingProvider())
    result = _run(spec, description="失败的调研")
    assert result.status == "error"
    assert result.summary == "[ERROR] 子代理失败：失败的调研（阶段成本上限）", result.summary
    assert result.output == BUDGET_OUTPUT, result.output
