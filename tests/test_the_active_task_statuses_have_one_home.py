"""M8-T372 — 「任务还在跑」这个事实只有一个家

**一个事实两个家，等于这个事实没有主人。** ✓

"这个任务还在跑吗" ✓ 是关于任务状态的**第三个问题** ✓：

* 全部状态 ✓ → `TASK_STATUSES` ✓（`minicc/agent/protocol.py` ✓）；
* 已结束的状态 ✓ → `TERMINAL_TASK_STATUSES` ✓（同一个模块 ✓）；
* **还在跑的状态** ✓ → **没有名字** ✓。

于是它被**手写了十二遍** ✓：后端七处 ✓（`task_manager.py` 六处 ✓ /
`web.py` 一处 ✓），前端五处 ✓（`panels/index.js` 三处 ✓ / `chat/stream.js`
两处 ✓）——每一处都得**自己拼对** `{"queued", "running"}` ✓。

这一批 ✓：给它一个家 ✓（`ACTIVE_TASK_STATUSES` ✓）✓，并且**推导**出来 ✓
（`TASK_STATUSES - TERMINAL_TASK_STATUSES` ✓）——家里有原料 ✓，只是没人用 ✓。

门禁是**结构断言** ✓：任何 Python 或 JS 模块都**不许**再手写这份集合 ✓。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
WEB_SRC = REPO / "web" / "src"

#: The statuses that mean "the task has not finished yet".
ACTIVE = frozenset({"queued", "running"})


def _python_sets(path: Path) -> list[tuple[int, str, set[str]]]:
    """Every set/discard literal in a module, with its line and members."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return []
    found: list[tuple[int, str, set[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Set):
            continue
        members = {
            element.value
            for element in node.elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        }
        if members:
            found.append((node.lineno, ast.unparse(node), members))
    return found


def test_the_backend_has_one_home_for_the_active_statuses() -> None:
    """The home exists, and it is derived from the two named facts."""
    from minicc.agent.protocol import (
        ACTIVE_TASK_STATUSES,
        TASK_STATUSES,
        TERMINAL_TASK_STATUSES,
    )

    assert ACTIVE_TASK_STATUSES == frozenset(TASK_STATUSES - TERMINAL_TASK_STATUSES), (
        "the active statuses must be derived from the two named facts, not "
        "written out a second time"
    )
    assert ACTIVE_TASK_STATUSES == ACTIVE, (
        f"the active statuses are {sorted(ACTIVE_TASK_STATUSES)}, "
        f"expected {sorted(ACTIVE)}"
    )


def test_no_python_module_writes_the_active_statuses_out_by_hand() -> None:
    """No module may spell the "still running" set out itself."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for lineno, text, members in _python_sets(path):
            if members == set(ACTIVE):
                offenders.append(f"{path.relative_to(REPO)}:{lineno}: {text}")
    assert not offenders, (
        "these modules write out the active task statuses by hand; the one "
        f"home is ACTIVE_TASK_STATUSES in minicc/agent/protocol.py: "
        + "; ".join(offenders)
    )


def test_no_frontend_module_writes_the_active_statuses_out_by_hand() -> None:
    """The same discipline on the other face (the frontend cannot import it)."""
    offenders: list[str] = []
    for path in sorted(WEB_SRC.rglob("*.js")):
        source = path.read_text(encoding="utf-8")
        for match in re.finditer(r"\[[^\]\[]*\]", source):
            members = set(re.findall(r'"([a-z_]+)"', match.group(0)))
            if members == set(ACTIVE):
                line = source[: match.start()].count("\n") + 1
                offenders.append(f"{path.relative_to(REPO)}:{line}: {match.group(0)}")
    assert not offenders, (
        "these frontend modules write out the active task statuses by hand; "
        "the one home is ACTIVE_TASK_STATUSES in web/src/core/state.js: "
        + "; ".join(offenders)
    )


def test_the_frontend_home_derives_it_too() -> None:
    """The frontend's home derives the set the same way the backend does."""
    source = (WEB_SRC / "core" / "state.js").read_text(encoding="utf-8")
    assert "export const ACTIVE_TASK_STATUSES" in source, (
        "web/src/core/state.js must export ACTIVE_TASK_STATUSES"
    )
    assert "TERMINAL_TASK_STATUSES.has(status)" in source, (
        "the frontend's active statuses must be derived from the terminal "
        "ones, not written out"
    )


def test_the_two_faces_agree_on_the_active_statuses() -> None:
    """The frontend's mirror must be the backend's set, not a lookalike."""
    from minicc.agent.protocol import ACTIVE_TASK_STATUSES

    source = (WEB_SRC / "core" / "state.js").read_text(encoding="utf-8")
    block = re.search(
        r"export const TASK_STATUSES = new Set\(\[([\s\S]*?)\]\);", source
    )
    assert block, "the frontend must mirror the backend's TASK_STATUSES"
    frontend_statuses = set(re.findall(r'"([a-z_]+)"', block.group(1)))
    terminal_block = re.search(
        r"export const TERMINAL_TASK_STATUSES = new Set\(\[([\s\S]*?)\]\);", source
    )
    assert terminal_block, "the frontend must mirror the backend's TERMINAL_TASK_STATUSES"
    frontend_terminal = set(re.findall(r'"([a-z_]+)"', terminal_block.group(1)))
    frontend_active = frontend_statuses - frontend_terminal
    assert frontend_active == set(ACTIVE_TASK_STATUSES), (
        "the two faces disagree about which tasks are still running: "
        f"backend {sorted(ACTIVE_TASK_STATUSES)} vs frontend {sorted(frontend_active)}"
    )
