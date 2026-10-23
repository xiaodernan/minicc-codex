"""M8-T411 — 运行时 trace 事件记录四十八个家：四十六处七键字面量加两个近似 builder"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/trace.py"

#: Every module that emits a trace event and now asks the home for it.
EMITTERS = (
    "minicc/agent/loop.py",
    "minicc/agent/subagent.py",
    "minicc/llm/anthropic_provider.py",
    "minicc/llm/fake.py",
    "minicc/llm/openai_provider.py",
    "minicc/main.py",
    "minicc/task_manager.py",
    "minicc/web.py",
)


def _trace_dict_literals(path: Path) -> list[ast.Dict]:
    """Dict literals that spell ``"kind": "trace"`` - the record's signature."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[ast.Dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if (
                isinstance(key, ast.Constant) and key.value == "kind"
                and isinstance(value, ast.Constant) and value.value == "trace"
            ):
                found.append(node)
                break
    return found


def test_the_home_builds_the_record() -> None:
    """The constructor owns the seven keys and their order."""
    from minicc.trace import trace_event

    event = trace_event(
        name="planner", status="error", phase="planning",
        code="planner_fixed_fallback", summary="回退固定模板",
        detail={"reason": "unsafe"},
    )
    assert list(event) == [
        "kind", "name", "status", "phase", "code", "summary", "detail",
    ]
    assert event["kind"] == "trace"
    assert event["detail"] == {"reason": "unsafe"}


def test_a_milestone_without_a_payload_omits_detail() -> None:
    """The loop's old shape: six keys, no ``detail`` key at all."""
    from minicc.trace import trace_event

    event = trace_event("agent", "ok", "answering", "milestone", "开始回答")
    assert "detail" not in event
    assert list(event) == ["kind", "name", "status", "phase", "code", "summary"]


def test_every_emitter_asks_the_home() -> None:
    """All eight emitting modules import the constructor."""
    for name in EMITTERS:
        source = (PACKAGE / name.removeprefix("minicc/")).read_text(encoding="utf-8")
        assert "trace_event" in source, (
            f"{name} must ask the one home for the trace event shape"
        )


def test_the_record_is_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second shape.

    The count is exact (not "all inside the home") because the T396 lesson
    applies: the loop's own six-key builder sat in a *different* module from
    the forty-six seven-key literals, and both had to be caught.
    """
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(REPO).as_posix()
        for node in _trace_dict_literals(path):
            offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the trace event record is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )
