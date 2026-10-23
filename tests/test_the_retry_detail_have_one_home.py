"""M8-T443 — provider 重试详情两键两个家：真实重试与 fake 模仿各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/llm/base.py"

FIELDS = {"attempt", "retry_limit"}


def test_the_home_builds_the_detail() -> None:
    """The constructor owns the two keys."""
    from minicc.llm.base import retry_detail

    assert retry_detail(2, 3) == {"attempt": 2, "retry_limit": 3}


def test_the_two_keys_are_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second detail shape."""
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
            if keys == FIELDS:
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the provider-retry detail is spelled by hand outside its one "
        "home: " + ", ".join(offenders)
    )


def test_both_sites_ask_the_home() -> None:
    """The real retry, the fake's imitation, and the definition itself."""
    for site in ("minicc/llm/openai_provider.py", "minicc/llm/fake.py"):
        source = (REPO / site).read_text(encoding="utf-8")
        assert source.count("retry_detail(") == 1, (
            f"{site} must call the home exactly once, found "
            f"{source.count('retry_detail(')}"
        )
