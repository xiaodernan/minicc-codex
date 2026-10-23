"""M8-T413 — 计量用量记录六个家：两个 provider 的解析器与假 provider 常量表各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/llm/usage.py"

FIELDS = {"prompt_tokens", "completion_tokens", "total_tokens"}

#: Every module that builds a measured usage record and now asks the home.
BUILDERS = (
    "minicc/llm/anthropic_provider.py",
    "minicc/llm/fake.py",
    "minicc/llm/openai_provider.py",
)


def test_the_home_builds_the_record() -> None:
    """The constructor owns the three keys, and the sum is the default total."""
    from minicc.llm.usage import measured_usage

    assert measured_usage(120, 20) == {
        "prompt_tokens": 120, "completion_tokens": 20, "total_tokens": 140,
    }
    assert measured_usage(10, 5, 99)["total_tokens"] == 99, (
        "a gateway-reported total must win over the sum"
    )


def test_the_estimated_flag_still_rides_on_the_same_counters() -> None:
    """T409's four-key record now derives from the three-key one."""
    from minicc.llm.usage import estimated_usage

    record = estimated_usage(10, 5)
    assert record == {
        "prompt_tokens": 10, "completion_tokens": 5,
        "total_tokens": 15, "estimated": True,
    }


def test_every_builder_asks_the_home() -> None:
    """All three emitting modules reference the constructor."""
    for name in BUILDERS:
        source = (PACKAGE / name.removeprefix("minicc/")).read_text(encoding="utf-8")
        assert "measured_usage" in source, (
            f"{name} must ask the one home for the measured usage shape"
        )


def test_the_record_is_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second set of counters.

    Six copies existed: the OpenAI parser's zero fallback and its normalized
    record, the Anthropic normalizer's two-step shape (two keys, then a
    separate total assignment), and three fixture rows whose totals were
    kept equal to their parts by a comment alone.  A row whose total
    disagrees with its parts is billed without complaint.
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
            keys = {
                key.value
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            if keys == FIELDS:
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the measured usage record is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )
