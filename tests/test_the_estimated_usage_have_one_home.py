"""M8-T409 — 估算用量记录的四个键两个家：循环与 Web 规划路由各手抄一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/llm/usage.py"

FIELDS = {"prompt_tokens", "completion_tokens", "total_tokens", "estimated"}

#: The two readers that build the record: the agent loop (a gateway that
#: answers without usage) and the web planner route (a planner call that
#: rides outside the loop).
READERS = ("minicc/agent/loop.py", "minicc/web.py")


def test_the_home_builds_the_four_key_record() -> None:
    """usage.py owns the shape in one builder, and the arithmetic with it."""
    from minicc.llm.usage import estimated_usage

    record = estimated_usage(10, 5)
    assert set(record) == FIELDS
    assert record["prompt_tokens"] == 10
    assert record["completion_tokens"] == 5
    assert record["total_tokens"] == 15
    assert record["estimated"] is True


def test_both_readers_ask_the_home() -> None:
    """Both faces import the builder instead of spelling the dict out."""
    for name in READERS:
        source = (PACKAGE / name.removeprefix("minicc/")).read_text(encoding="utf-8")
        assert "estimated_usage" in source, (
            f"{name} must ask the one home for the estimated usage shape"
        )


def test_no_module_writes_the_four_keys_by_hand() -> None:
    """A second copy is a second shape the aggregation can miss a field of.

    The first version of the T396-style gate watched only ``startswith``
    families; here the risk is the opposite one - a reader that builds the
    dict inline and quietly forgets a key the aggregator later reads as a
    missing field.

    M8-T413: the home stopped spelling the four keys as one literal and
    derives them from the three-key ``measured_usage`` plus the flag, which
    is strictly stronger - so the census now demands *zero* hand-written
    four-key literals anywhere, and the derived form in the home.
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
            if len(node.keys) >= 3 and keys == FIELDS:
                offenders.append(f"{relative}:{node.lineno}")
    assert not offenders, (
        "the estimated usage record is spelled by hand outside its one "
        "builder: " + ", ".join(offenders)
    )
    home_source = (REPO / HOME).read_text(encoding="utf-8")
    assert "{**measured_usage(" in home_source and '"estimated": True' in home_source, (
        "the four-key record must be derived from the three-key home plus "
        "the flag, not spelled out"
    )
