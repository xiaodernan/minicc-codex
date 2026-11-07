"""M8-T554 — 会话持久化触发事件集只有一个家。

「哪些 trace code 值得把对话重新落盘」这个事实，之前只在 web 模块的
``AgentService._chat_locked`` 事件闭包里拼了一份 code 集合：事实本身
（只有这些事件之后对话才可能需要被 resume）没有第二个人知道，而事件
词汇本来就是 agent 协议层（``minicc/agent/protocol.py``）的——一个事实
该有两个主人家，就是同族缺陷。

红先行：落地前 web 闭包手抄集合，且协议层没有答案，本门对全红。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/agent/protocol.py"

SESSION_PERSIST_TRACE_CODES = frozenset({
    "tool_round_finished",
    "verification_required_before_finish",
    "provider_stream_error",
    "budget_exceeded",
    "stagnation_guard",
    "run_finished",
})


def test_the_home_answers_the_persist_question() -> None:
    """The one home owns the predicate; it answers yes only for durable codes."""
    from minicc.agent.protocol import session_persist_required

    for code in sorted(SESSION_PERSIST_TRACE_CODES):
        assert session_persist_required({"code": code}) is True, code
    for code in ("model_decision", "tool_round_started", "milestone", ""):
        assert session_persist_required({"code": code}) is False, code


def test_the_web_face_asks_the_home() -> None:
    """web 的 on_trace 不再手抄集合，而是问一问唯一家。"""
    source = (PACKAGE / "web.py").read_text(encoding="utf-8")
    assert "session_persist_required(event)" in source, (
        "minicc/web.py must ask the one home (minicc/agent/protocol.py) "
        "whether a trace event requires a session re-save"
    )
    assert "SESSION_PERSIST_TRACE_CODES" not in source, (
        "minicc/web.py must not spell the persist-worthy code set itself"
    )


def test_no_module_spells_the_set_outside_the_home() -> None:
    """One spelling of the set, in the home - a second one is a second home."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Set):
                continue
            elements = frozenset(
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
            if elements == SESSION_PERSIST_TRACE_CODES:
                if relative != HOME:
                    offenders.append(f"{relative}:{node.lineno}")
    assert not offenders, (
        "the session-persist trace-code set is spelled outside its one home "
        f"({HOME}): " + ", ".join(offenders)
    )
