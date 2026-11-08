"""M8-T615 — the budget_exceeded trace code has one home.

``budget_exceeded`` is minted by the agent loop (5 sites) and by the protocol
helper/set; the web sink also treats it as a session-persist trigger via
``SESSION_PERSIST_TRACE_CODES``.  The same fact must not be re-spelled as bare
``code="budget_exceeded"`` literals outside the protocol home.

The home is ``minicc.agent.protocol.BUDGET_EXCEEDED_CODE``.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "agent" / "protocol.py"


def test_the_home_defines_the_code() -> None:
    from minicc.agent.protocol import BUDGET_EXCEEDED_CODE

    assert BUDGET_EXCEEDED_CODE == "budget_exceeded"


def test_no_bare_budget_exceeded_code_literal_in_minicc() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if path.resolve() == HOME.resolve():
            continue
        try:
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src, filename=str(path))
        except Exception:
            continue
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "code":
                if isinstance(node.value, ast.Constant) and node.value.value == "budget_exceeded":
                    offenders.append(f"{rel}:{node.lineno} code='budget_exceeded'")
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values):
                    if (
                        isinstance(k, ast.Constant)
                        and k.value == "code"
                        and isinstance(v, ast.Constant)
                        and v.value == "budget_exceeded"
                    ):
                        offenders.append(f"{rel}:{v.lineno} dict code 'budget_exceeded'")
    assert offenders == [], (
        "bare budget_exceeded code literals outside protocol.py - ask "
        "BUDGET_EXCEEDED_CODE:\n" + "\n".join(offenders)
    )
