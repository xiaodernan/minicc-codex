"""M8-T406 — 推理力别名表两个家：config 归一器与 provider 构造器各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/config.py"

ALIASES = {
    "standard": "mid",
    "medium": "mid",
    "very-high": "xhigh",
    "veryhigh": "xhigh",
    "maximum": "max",
    "高": "high",
    "极高": "xhigh",
    "最高": "max",
}


def test_the_home_exists_in_config() -> None:
    """config.py owns the alias table, and every alias lands on a real effort."""
    from minicc.config import REASONING_EFFORTS, REASONING_EFFORT_ALIASES

    assert REASONING_EFFORT_ALIASES == ALIASES
    assert set(REASONING_EFFORT_ALIASES.values()) <= set(REASONING_EFFORTS), (
        "an alias maps onto an effort the vocabulary does not have"
    )


def test_the_provider_imports_the_same_table() -> None:
    """The provider constructor asks the home, not a copy of it."""
    from minicc.config import REASONING_EFFORT_ALIASES
    from minicc.llm import openai_provider

    assert openai_provider.REASONING_EFFORT_ALIASES is REASONING_EFFORT_ALIASES


def test_no_module_inlines_the_alias_table() -> None:
    """No module spells the alias mapping as a literal outside the home."""
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
            if len(keys) >= 3 and keys == set(ALIASES):
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the reasoning-effort alias table is spelled inline outside the one "
        "declaration: " + ", ".join(offenders)
    )


def test_aliases_still_normalize_on_both_readers() -> None:
    """Behavior unchanged: the same spellings land on the same efforts."""
    from minicc.config import normalize_reasoning_effort

    assert normalize_reasoning_effort("medium") == "mid"
    assert normalize_reasoning_effort("very-high") == "xhigh"
    assert normalize_reasoning_effort("极高") == "xhigh"
    assert normalize_reasoning_effort("maximum") == "max"
    assert normalize_reasoning_effort("high") == "high"
    with pytest.raises(ValueError, match="reasoning effort 非法"):
        normalize_reasoning_effort("extreme")

