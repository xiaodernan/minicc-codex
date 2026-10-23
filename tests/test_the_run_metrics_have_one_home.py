"""M8-T418 — 运行指标汇总两个家：hook 拦截早退与正常收尾各手抄一份五键"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/agent/loop.py"

FIELDS = {"turns", "tool_calls", "trace_events", "tokens", "budget"}


def test_the_home_builds_the_summary() -> None:
    """The constructor owns the five keys of a run's metrics summary."""
    from minicc.agent.loop import TurnResult, _run_metrics
    from minicc.agent.state import Budget

    result = TurnResult(answer="a")
    result.turns = 3
    result.tool_calls_total = 5
    result.trace_events = [{"kind": "trace"}]
    result.tokens_used = {"total_tokens": 42}
    metrics = _run_metrics(
        result, Budget(max_turns=10), turns=result.turns,
        tool_calls=result.tool_calls_total,
    )
    assert metrics == {
        "turns": 3,
        "tool_calls": 5,
        "trace_events": 1,
        "tokens": {"total_tokens": 42},
        "budget": metrics["budget"],
    }, metrics
    assert metrics["budget"], metrics


def test_the_summary_is_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second metrics shape.

    The two copies sat in the two exits of ``run_agent``: the hook-blocked
    early return (hardcoded zero turns and zero tool calls) and the normal
    end-of-run summary.  A key the early exit forgets makes a blocked run
    look like a run that measured nothing, which is exactly what it is not.
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
        "the run metrics summary is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )


def test_both_exits_ask_the_home() -> None:
    """Both exits call the constructor - the census only counts literals."""
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("_run_metrics(") == 3, (
        "the helper definition plus both exits must be the only spellings"
    )
