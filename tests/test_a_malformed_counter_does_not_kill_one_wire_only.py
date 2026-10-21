"""M8-T358 — 网关给的计数器是不可信输入：两条线不许一条活一条死

网关偶尔会把 token 计数写成**不是数字的东西**（对象 ✓ / 数组 ✓ / 非数字字符串
✓）。两条线对它的处理原本不同：

* OpenAI 兼容那条线把每个计数器包在 ``try: int(...) except (TypeError,
  ValueError)`` 里 ✓ → 读不出来就**不写那个键** ✓；
* Anthropic 那条线是裸的 ``int(usage.get("input_tokens") or 0)`` ✓ → 一个对象就
  抛 **TypeError** ✓ → provider 抛 ✓ → **整轮崩掉** ✓。

同一个畸形计数器，一条线安静地忽略、另一条线把任务打死 ✗。

本门钉住：两条线对同一份畸形 usage 都**不抛** ✓；OpenAI 兼容那条线仍然
"读不出来就不写那个键" ✓；Anthropic 那条线按它的约定"没读到缓存就是 0" ✓。
"""

from __future__ import annotations

from typing import Any

from minicc.llm.anthropic_provider import _normalize_usage
from minicc.llm.openai_provider import _parse_usage
from minicc.llm.usage import token_count


def test_a_malformed_counter_never_raises() -> None:
    """The observable: a bad counter cannot kill the turn."""
    broken = {
        "input_tokens": {"nope": 1},
        "output_tokens": ["nope"],
        "cache_read_input_tokens": "not a number",
        "cache_creation_input_tokens": object(),
    }
    normalized = _normalize_usage(broken)  # type: ignore[arg-type]
    assert normalized["prompt_tokens"] == 0, normalized
    assert normalized["completion_tokens"] == 0, normalized
    assert normalized["prompt_cache_hit_tokens"] == 0, normalized

    parsed = _parse_usage(broken)  # type: ignore[arg-type]
    # Both wires agree on the number: a counter we cannot read is 0.
    assert parsed["prompt_tokens"] == 0, parsed
    # The OpenAI-compatible wire's convention for the cache counters: a
    # counter we cannot read is simply not written.
    assert "prompt_cache_hit_tokens" not in parsed, parsed


def test_a_well_formed_counter_is_read_normally() -> None:
    """The control: the ordinary path is untouched."""
    normalized = _normalize_usage({
        "input_tokens": 100,
        "output_tokens": 20,
        "cache_read_input_tokens": 80,
    })  # type: ignore[arg-type]
    assert normalized["prompt_tokens"] == 180, normalized
    assert normalized["prompt_cache_hit_tokens"] == 80, normalized
    assert normalized["total_tokens"] == 200, normalized


def test_the_shared_reader_keeps_its_two_defaults() -> None:
    """One home, two defaults: "not reported" and "reported as nothing"."""
    assert token_count("12") == 12
    assert token_count(12.7) == 12
    assert token_count({"a": 1}) is None
    assert token_count({"a": 1}, 0) == 0
    assert token_count("not a number") is None
    assert token_count("not a number", 0) == 0
    # The conversion is int() exactly as before - a bool still reads as 1.
    assert token_count(True) == 1
    assert token_count(None, 0) == 0
