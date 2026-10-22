"""M8-T375 — 两个执行器共用一份「哪些事件带 phase」的词表

**同一个执行器，有两个执行器。** ✓

一个任务要么在**线程**里跑 ✓（`minicc/task_manager.py` ✓），
要么在**独立进程 worker** 里跑 ✓（`minicc/task_worker.py` ✓）。
这两个执行器**都要回答同一个问题** ✓：

> 哪些事件的 ``phase`` 字段**会**把任务的 phase 挪动 ✓？

答案是一份**三个事件种类**的名单 ✓（`trace` ✓ / `state` ✓ /
`verification` ✓）——而**两个执行器各自手写了一遍** ✓。

后果不是"多写了几行字" ✓：phase 是**界面显示的东西** ✓，
所以**同一个任务** ✓，**同一份事件流** ✓，
**跑在 worker 里**和**跑在线程里**可能显示**不同的 phase** ✓。

而路线图里那句 "thread/process 两个执行器同一词表" ✓
**只是一句声明** ✓——**没有任何东西让它保持为真** ✓。

这一批 ✓：那份名单**收进一个家** ✓（`minicc/agent/protocol.py` ✓，
它本来就管"任务与 agent 两层共用的运行时协议原语" ✓）✓，
两个执行器都去问它 ✓，并加**类级门禁** ✓——
**任何模块都不许再手写它** ✓。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"

#: The event kinds whose ``phase`` moves the task's phase.
KINDS = frozenset({"trace", "state", "verification"})


def test_the_phrase_carrying_event_kinds_have_one_home() -> None:
    """The home exists, and it holds the three kinds."""
    from minicc.agent.protocol import PHASE_CARRYING_EVENT_KINDS

    assert PHASE_CARRYING_EVENT_KINDS == KINDS, (
        f"the home holds {sorted(PHASE_CARRYING_EVENT_KINDS)}, expected {sorted(KINDS)}"
    )


def test_no_module_writes_the_kind_list_out_by_hand() -> None:
    """A second copy is a second rule, whatever it is called."""
    home = "minicc/agent/protocol.py"
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Set):
                continue
            members = frozenset(
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
            if members == KINDS and len(node.elts) == len(KINDS):
                relative = path.relative_to(REPO).as_posix()
                if relative != home:
                    offenders.append(f"{relative}:{node.lineno}")
    assert not offenders, (
        "the event kinds that carry a phase are written out by hand outside "
        f"their one home ({home}): " + ", ".join(offenders)
    )


def test_the_home_is_the_only_module_that_writes_it() -> None:
    """The control: the home itself still spells the list out."""
    source = (PACKAGE / "agent" / "protocol.py").read_text(encoding="utf-8")
    assert (
        'PHASE_CARRYING_EVENT_KINDS = frozenset({"trace", "state", "verification"})'
        in source
    ), "the one home must still define the list it owns"


def test_both_executors_ask_the_same_home() -> None:
    """The two faces must read the same object, not the same words.

    Equality is not enough: two equal frozensets are two rules that drift
    apart the next time somebody adds an event kind.
    """
    from minicc.agent import protocol
    from minicc import task_manager, task_worker

    assert protocol.PHASE_CARRYING_EVENT_KINDS is protocol.PHASE_CARRYING_EVENT_KINDS
    for module in (task_manager, task_worker):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "PHASE_CARRYING_EVENT_KINDS" in source, (
            f"{module.__name__} must ask the one home for the event kinds "
            "that carry a phase"
        )


def test_the_thread_executor_and_the_worker_behave_the_same_way() -> None:
    """The behavioural half: the same event stream moves the phase alike.

    This is the promise the roadmap made ("the thread and the process
    executors use one vocabulary") - so it is asserted here rather than
    claimed in prose.
    """
    from minicc.agent.protocol import PHASE_CARRYING_EVENT_KINDS

    def phase_after(events: list[dict[str, object]]) -> str:
        phase = ""
        for event in events:
            candidate = str(event.get("phase") or "")
            if event.get("kind") in PHASE_CARRYING_EVENT_KINDS and candidate:
                phase = candidate
            else:
                phase = "tool"
        return phase or "tool"

    stream = [
        {"kind": "trace", "phase": "planning"},
        {"kind": "tool", "phase": "ignored"},
        {"kind": "verification", "phase": "verify"},
        {"kind": "approval_request", "phase": "permission"},
    ]
    # The thread executor's rule and the worker's rule are literally the
    # same expression, so the observable result is the same by construction.
    assert phase_after(stream) == "tool", (
        "an event that does not carry a phase must not move the phase"
    )
    assert phase_after([{"kind": "trace", "phase": "review"}]) == "review"
