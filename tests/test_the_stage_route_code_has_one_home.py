"""M8-T614 — the stage_route trace code has one home.

Both the CLI (main.py) and the web runtime (web.py) emit ``code="stage_route"``
to record the model/effort chosen for a routed stage. The string is the same
fact on two emitters.

The home is ``minicc.agent.protocol.STAGE_ROUTE_CODE``.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "agent" / "protocol.py"


def test_the_home_defines_the_code() -> None:
    from minicc.agent.protocol import STAGE_ROUTE_CODE

    assert STAGE_ROUTE_CODE == "stage_route"


def test_no_bare_stage_route_code_literal_in_minicc() -> None:
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
                if isinstance(node.value, ast.Constant) and node.value.value == "stage_route":
                    offenders.append(f"{rel}:{node.lineno} code='stage_route'")
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values):
                    if (
                        isinstance(k, ast.Constant)
                        and k.value == "code"
                        and isinstance(v, ast.Constant)
                        and v.value == "stage_route"
                    ):
                        offenders.append(f"{rel}:{v.lineno} dict code 'stage_route'")
    assert offenders == [], (
        "bare stage_route code literals outside protocol.py - ask "
        "STAGE_ROUTE_CODE:\n" + "\n".join(offenders)
    )
