"""M8-T519 — CORE_WRITE_TOOLS 一个键三个家：graph/loop/subagent 统一导入"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"

CORE_WRITE_TOOLS = frozenset({"write_file", "edit_file"})


def test_the_core_write_tools_exist_in_tool_policy() -> None:
    """CORE_WRITE_TOOLS exists in tool_policy.py."""
    from minicc.agent.tool_policy import CORE_WRITE_TOOLS as PolicyCore
    assert PolicyCore == CORE_WRITE_TOOLS


def test_graph_imports_from_tool_policy() -> None:
    """graph.py imports CORE_WRITE_TOOLS from tool_policy."""
    from minicc.agent.graph import WRITE_DAG_TOOLS
    from minicc.agent.tool_policy import CORE_WRITE_TOOLS as Home
    assert WRITE_DAG_TOOLS is Home


def test_loop_imports_from_tool_policy() -> None:
    """loop.py imports CORE_WRITE_TOOLS from tool_policy."""
    from minicc.agent.loop import PARALLEL_SAFE_WRITE_TOOLS
    from minicc.agent.tool_policy import CORE_WRITE_TOOLS as Home
    assert PARALLEL_SAFE_WRITE_TOOLS is Home


def test_subagent_imports_from_tool_policy() -> None:
    """subagent.py imports CORE_WRITE_TOOLS from tool_policy."""
    from minicc.agent.subagent import SUBAGENT_WRITE_TOOLS
    from minicc.agent.tool_policy import CORE_WRITE_TOOLS as Home
    assert SUBAGENT_WRITE_TOOLS is Home


def test_no_inline_core_write_tools_anywhere() -> None:
    """No module has inline {'write_file', 'edit_file'} set (outside tool_policy)."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Set):
                continue
            elements = frozenset(
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
            if elements == CORE_WRITE_TOOLS:
                relative = path.relative_to(REPO).as_posix()
                if relative != "minicc/agent/tool_policy.py":
                    offenders.append(f"{relative}:{node.lineno}")

    assert not offenders, (
        "Inline core write tools sets found outside their one home "
        "(minicc/agent/tool_policy.py): " + ", ".join(offenders)
    )


def test_core_write_tools_is_subset_of_write_tool_names() -> None:
    """CORE_WRITE_TOOLS is a subset of WRITE_TOOL_NAMES."""
    from minicc.agent.tool_policy import WRITE_TOOL_NAMES
    assert CORE_WRITE_TOOLS <= WRITE_TOOL_NAMES