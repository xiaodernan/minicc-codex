"""M8-T420 — 渠道计数器零形状六个家：两个 provider 各自抄了三份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/llm/usage.py"

FIELDS = {"requests", "total_tokens"}
SITES = ("minicc/llm/anthropic_provider.py", "minicc/llm/openai_provider.py")


def test_the_home_builds_a_fresh_zeroed_counter() -> None:
    """The constructor owns the shape, and every call is a fresh object."""
    from minicc.llm.usage import channel_counter

    counter = channel_counter()
    assert set(counter) == FIELDS
    assert counter["requests"] == 0
    assert counter["total_tokens"] == 0
    assert channel_counter() is not counter, (
        "the two channel seeds in __init__ must not share one dict"
    )


def test_the_zeroed_counter_is_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second zero shape."""
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
            keys = {
                key.value
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            if keys != FIELDS:
                continue
            values = [v for v in node.values if isinstance(v, ast.Constant)]
            if len(values) != len(node.values) or any(v.value != 0 for v in values):
                continue
            offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the zeroed channel counter is spelled by hand outside its one "
        "home: " + ", ".join(offenders)
    )


def test_every_seeding_site_asks_the_home() -> None:
    """Each provider seeds two channels in __init__ plus one setdefault."""
    for site in SITES:
        source = (REPO / site).read_text(encoding="utf-8")
        assert source.count("channel_counter(") == 3, (
            f"{site} must call the home exactly three times (two channel "
            f"seeds plus the setdefault default), found "
            f"{source.count('channel_counter(')}"
        )
