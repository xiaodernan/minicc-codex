"""M8-T613 — the provider-retry trace code has one home.

Both LLM provider implementations (real OpenAI-compatible and the fake test
double) emit ``code="provider_retry"`` when they retry a transient failure.
The string is the same fact on two emitters; spelling it twice lets them drift.

The home is ``minicc.agent.protocol.PROVIDER_RETRY_CODE``.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "agent" / "protocol.py"


def test_the_home_defines_the_code() -> None:
    from minicc.agent.protocol import PROVIDER_RETRY_CODE

    assert PROVIDER_RETRY_CODE == "provider_retry"


def test_no_bare_provider_retry_code_literal_in_minicc() -> None:
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
                if isinstance(node.value, ast.Constant) and node.value.value == "provider_retry":
                    offenders.append(f"{rel}:{node.lineno} code='provider_retry'")
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values):
                    if (
                        isinstance(k, ast.Constant)
                        and k.value == "code"
                        and isinstance(v, ast.Constant)
                        and v.value == "provider_retry"
                    ):
                        offenders.append(f"{rel}:{v.lineno} dict code 'provider_retry'")
    assert offenders == [], (
        "bare provider_retry code literals outside protocol.py - ask "
        "PROVIDER_RETRY_CODE:\n" + "\n".join(offenders)
    )
