"""M8-T380 — "任务没成功"也是个词表：failed 或 interrupted

**一个事实两个家，顺序不同也是两个家。** ✓

`task_manager.py` 里出现了 **6 次** `{"failed", "interrupted"}`（或倒序 `{"interrupted", "failed"}`）。
它们各自手写，且**没有名字**。

其实这是个明确的语义：**"任务没成功"** = 失败 **或** 被中断（取消不算，取消是主动放弃）。

`protocol.py` 已有 `TERMINAL_TASK_STATUSES`（已结束的）与 `ACTIVE_TASK_STATUSES`（进行中的），
唯独**"结束且没成功"**这个正当问题**没名字**。

这一批：给它起个名字 `TASK_UNSUCCESSFUL_STATUSES`，放在 `protocol.py`；
6 处全改问那个家。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"

# The exact set we consider "task unsuccessful"
UNSUCCESSFUL = frozenset({"failed", "interrupted"})


def test_the_task_unsuccessful_statuses_have_one_home() -> None:
    """The home exists and holds exactly the two statuses."""
    from minicc.agent.protocol import TASK_UNSUCCESSFUL_STATUSES

    assert TASK_UNSUCCESSFUL_STATUSES == UNSUCCESSFUL, (
        f"the unsuccessful statuses are {sorted(TASK_UNSUCCESSFUL_STATUSES)}, "
        f"expected {sorted(UNSUCCESSFUL)}"
    )


def test_no_module_writes_the_unsuccessful_statuses_out_by_hand() -> None:
    """No module may spell out the set by hand; it must import from protocol."""
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
            if members == UNSUCCESSFUL and len(node.elts) == 2:
                relative = path.relative_to(REPO).as_posix()
                if relative != "minicc/agent/protocol.py":
                    offenders.append(f"{relative}:{node.lineno}")
    assert not offenders, (
        "the unsuccessful task statuses are written out by hand outside "
        "their one home (minicc/agent/protocol.py): " + ", ".join(offenders)
    )


def test_the_home_is_in_protocol_py() -> None:
    """The home is in protocol.py and is exported."""
    import minicc.agent.protocol as protocol

    assert hasattr(protocol, "TASK_UNSUCCESSFUL_STATUSES"), (
        "protocol must export TASK_UNSUCCESSFUL_STATUSES"
    )
    assert protocol.TASK_UNSUCCESSFUL_STATUSES == frozenset({"failed", "interrupted"})