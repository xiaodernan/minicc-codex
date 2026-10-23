"""M8-T397 — 「需要授权的风险」两个家：audit 的授权门与 CLI 的审批 prompt 各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/tools/registry.py"

AUTH_RISKS = frozenset({"write", "exec"})


def test_the_home_exists_in_registry() -> None:
    """registry.py owns the authorization risks, derived from RISK_LEVELS."""
    from minicc.tools.registry import AUTHORIZATION_RISKS, RISK_LEVELS

    assert AUTHORIZATION_RISKS == AUTH_RISKS
    assert AUTHORIZATION_RISKS == frozenset(RISK_LEVELS) - {"readonly"}
    assert "readonly" not in AUTHORIZATION_RISKS


def test_both_faces_import_the_same_object() -> None:
    """audit.py and main.py ask the home, not a copy of it."""
    from minicc import audit, main
    from minicc.tools import registry

    assert audit.AUTHORIZATION_RISKS is registry.AUTHORIZATION_RISKS
    assert main.AUTHORIZATION_RISKS is registry.AUTHORIZATION_RISKS


def test_no_module_inlines_the_authorization_risks() -> None:
    """No module spells {"write", "exec"} as a literal outside the home."""
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
            if len(node.elts) >= 2 and elements == AUTH_RISKS:
                offenders.append(f"{relative}:{node.lineno}")
    assert not offenders, (
        "the authorization risks are spelled inline outside the one declaration: "
        + ", ".join(offenders)
    )


def test_the_gate_still_asks_for_write_and_exec() -> None:
    """tool_requires_authorization behavior is unchanged by the derivation."""
    from minicc.audit import tool_requires_authorization

    assert tool_requires_authorization("write_file", "write") is True
    assert tool_requires_authorization("bash", "exec") is True
    assert tool_requires_authorization("read_file", "readonly") is False
