"""M8-T425 — MCP clientInfo 两个家：stdio 与 HTTP 两条传输各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/mcp.py"


def test_the_home_builds_the_identity() -> None:
    """The constructor owns the pair and reads the package version."""
    from minicc import __version__
    from minicc.mcp import _client_info

    info = _client_info()
    assert info == {"name": "minicc", "version": __version__}
    # A fresh dict every time: callers must not share one identity record.
    assert _client_info() is not info


def test_the_identity_is_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second client.

    The fingerprint pins the name constant ``"minicc"``: the RPC
    server's ``serverInfo`` shares the two key names but names the
    server, a different role that stays where it is.
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
            fields = {
                key.value: value
                for key, value in zip(node.keys, node.values)
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            name_value = fields.get("name")
            if (
                set(fields) == {"name", "version"}
                and isinstance(name_value, ast.Constant)
                and name_value.value == "minicc"
            ):
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the MCP client identity is spelled by hand outside its one "
        "home: " + ", ".join(offenders)
    )


def test_both_transports_ask_the_home() -> None:
    """stdio and HTTP handshakes plus the definition itself."""
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("_client_info(") == 3, (
        "the definition plus the two initialize params are the only "
        f"spellings, found {source.count('_client_info(')}"
    )
