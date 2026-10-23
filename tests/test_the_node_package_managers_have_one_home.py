"""M8-T390 — Node 包管理器 {npm, pnpm, yarn}：写预测与证据判定两张脸各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/agent/tool_policy.py"

NODE_PACKAGE_MANAGERS = frozenset({"npm", "pnpm", "yarn"})


def test_the_home_exists_in_tool_policy() -> None:
    """tool_policy.py owns the three managers."""
    from minicc.agent.tool_policy import NODE_PACKAGE_MANAGERS as Home

    assert Home == NODE_PACKAGE_MANAGERS


def test_no_module_inlines_the_managers() -> None:
    """No module spells the trio as a literal outside the one declaration."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Set | ast.Tuple | ast.List):
                continue
            elements = frozenset(
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
            if len(node.elts) >= 2 and elements == NODE_PACKAGE_MANAGERS:
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the node package managers are spelled inline outside the one declaration: "
        + ", ".join(offenders)
    )


def test_both_faces_still_agree() -> None:
    """The write-prediction face and the evidence face still answer alike."""
    from minicc.agent.tool_policy import command_may_modify_workspace, is_verification_evidence

    # A check-only script is evidence and not a write.
    assert is_verification_evidence("bash", {"command": "npm run test:unit"}, "ok") is True
    assert command_may_modify_workspace("npm run test:unit") is False
    # A mutating script is a write and not evidence.
    assert command_may_modify_workspace("npm install left-pad") is True
    assert is_verification_evidence("bash", {"command": "npm install left-pad"}, "ok") is False
