"""M8-T401 — 网络子命令表内两对相同值：pip/pip3 与 powershell/pwsh 各写两遍"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/audit.py"

PIP_VERBS = frozenset({"install", "download", "wheel", "search"})
POWERSHELL_CMDLETS = frozenset({"invoke-webrequest", "invoke-restmethod", "iwr", "irm"})


def test_the_shared_sets_are_declared_once_and_shared() -> None:
    """Both spellings of a manager reference one declaration."""
    from minicc import audit

    assert audit._PIP_NETWORK_SUBCOMMANDS == PIP_VERBS
    assert audit._POWERSHELL_WEB_CMDLETS == POWERSHELL_CMDLETS
    table = audit.NETWORK_SUBCOMMANDS
    assert table["pip"] is table["pip3"] is audit._PIP_NETWORK_SUBCOMMANDS
    assert table["powershell"] is table["pwsh"] is audit._POWERSHELL_WEB_CMDLETS


def test_no_module_inlines_the_shared_sets() -> None:
    """Each shared set is spelled exactly once - its declaration in audit.py."""
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
            if len(node.elts) < 2:
                continue
            if elements in (PIP_VERBS, POWERSHELL_CMDLETS):
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 2 and all(item.startswith(HOME + ":") for item in offenders), (
        "the shared network verb sets are spelled inline outside their declarations: "
        + ", ".join(offenders)
    )


def test_the_gate_still_hears_the_network_verbs() -> None:
    """Behavior unchanged: both spellings of each manager still count."""
    from minicc.audit import command_uses_network

    assert command_uses_network("pip install requests") is True
    assert command_uses_network("pip3 install requests") is True
    assert command_uses_network('powershell -Command "iwr http://x"') is True
    assert command_uses_network("pwsh -c irm http://x") is True
    assert command_uses_network('git log --grep="git clone"') is False
    assert command_uses_network("python -m pytest -q") is False
