"""M8-T414 — 预算越限见证事件六个家：六个折叠各手抄一份三键 detail"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/agent/protocol.py"

FIELDS = {"stage", "error", "tokens_used"}

#: Every module that witnesses a budget trip and now asks the home.
WITNESSES = ("minicc/main.py", "minicc/task_manager.py", "minicc/web.py")


def test_the_home_builds_the_witness() -> None:
    """The constructor owns the event and its three-key detail."""
    from minicc.agent.protocol import budget_exceeded_event

    event = budget_exceeded_event(
        "planning", ValueError("boom"), {"total_tokens": 15},
        name="planner", phase="planning",
    )
    assert event["kind"] == "trace"
    assert event["name"] == "planner"
    assert event["status"] == "error"
    assert event["phase"] == "planning"
    assert event["code"] == "budget_exceeded"
    assert event["summary"] == "boom"
    assert event["detail"] == {
        "stage": "planning", "error": "boom", "tokens_used": {"total_tokens": 15},
    }


def test_a_trip_with_no_spend_still_carries_the_key() -> None:
    """The judge's old two-key detail is now the same three-key shape."""
    from minicc.agent.protocol import budget_exceeded_event

    event = budget_exceeded_event(
        "review", RuntimeError("x"), None, name="completion_judge", phase="review",
    )
    assert event["detail"] == {"stage": "review", "error": "x", "tokens_used": {}}


def test_every_witness_asks_the_home() -> None:
    """All three emitting modules reference the constructor."""
    for name in WITNESSES:
        source = (PACKAGE / name.removeprefix("minicc/")).read_text(encoding="utf-8")
        assert "budget_exceeded_event" in source, (
            f"{name} must ask the one home for the budget trip witness"
        )


def test_the_detail_is_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second witness shape.

    Six folds hand-wrote this event: the CLI subagent fold, the web subagent
    fold, the batch merge, the planner DAG, the planner fold, and the
    completion judge (whose copy dropped ``tokens_used`` altogether).  A
    detail that forgets the spend still publishes - the trip is on the
    timeline and the tokens look free.
    """
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = {
                key.value
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            if keys == FIELDS:
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the budget trip detail is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )
