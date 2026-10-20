"""M8-T315 — 没上报的计数不是 0，是**不知道**

`cache_summary` 的 docstring 写着 "without treating missing fields as zero"，
而它的实现里有一处正好这么做了：

```python
if hit is not None or miss is not None:
    hit_value = float(hit or 0)
    miss_value = float(miss or 0)      # ← 缺失的一侧被当成 0
    denominator = hit_value + miss_value
    result["cache_hit_rate"] = round(hit_value / denominator, 6) if denominator else 0.0
```

于是网关只上报一侧时（常态）：

* `{"prompt_cache_hit_tokens": 100}` → **命中率 1.0**（100%！）——那一侧**从来没
  被观测过**；
* `{"prompt_cache_miss_tokens": 50}` → **命中率 0.0**。

报告里出现了一个**从未发生过的断言**。

而 Anthropic 路径为了让"没上报"和"上报了 0"可区分，**无条件**写下
`prompt_cache_miss_tokens = input_tokens` —— 于是同一家网关在 Anthropic 路径
报"miss 0%"、在 OpenAI 路径报"unreported"：**同一件事，两个答案**。

本门禁钉住：两侧都知道才算命中率；一侧知道就说"不完整"；Anthropic 那一侧
的 0 是**真的 0**（没命中缓存）。
"""

from __future__ import annotations

import pytest

from minicc.llm.anthropic_provider import _normalize_usage
from minicc.llm.usage import aggregate_cache_summary, cache_summary


def test_one_reported_side_does_not_become_a_rate() -> None:
    """A rate needs both sides; one side is not zero, it is unknown."""
    only_hit = cache_summary({"prompt_cache_hit_tokens": 100})
    assert only_hit["cache_hit_rate"] is None, (
        f"a hit rate was invented from half the counters: {only_hit}"
    )
    assert only_hit["cache_status"] != "hit", only_hit
    assert only_hit["prompt_cache_hit_tokens"] == 100, only_hit

    only_miss = cache_summary({"prompt_cache_miss_tokens": 50})
    assert only_miss["cache_hit_rate"] is None, only_miss
    assert only_miss["prompt_cache_miss_tokens"] == 50, only_miss


def test_both_sides_still_give_a_rate() -> None:
    """The control: the ordinary case is unchanged."""
    both = cache_summary({"prompt_cache_hit_tokens": 100, "prompt_cache_miss_tokens": 100})
    assert both["cache_hit_rate"] == 0.5, both
    assert both["cache_status"] == "hit", both

    zero = cache_summary({"prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 0})
    assert zero["cache_status"] == "reported_zero", zero
    assert zero["cache_hit_rate"] == 0.0, zero


def test_nothing_reported_is_still_unreported() -> None:
    """The control: a gateway that sends no cache counters."""
    empty = cache_summary({"prompt_tokens": 100, "completion_tokens": 10})
    assert empty["cache_status"] == "unreported", empty
    assert empty["cache_hit_rate"] is None, empty


def test_the_anthropic_side_knows_that_zero_is_real() -> None:
    """``input_tokens`` is the miss side; no cache field means no hits."""
    usage = _normalize_usage({"input_tokens": 100, "output_tokens": 10})
    assert usage["prompt_cache_miss_tokens"] == 100, usage
    assert usage["prompt_cache_hit_tokens"] == 0, usage

    summary = cache_summary(usage)
    assert summary["cache_hit_rate"] == 0.0, summary
    assert summary["cache_status"] == "miss", summary


def test_the_anthropic_side_with_hits() -> None:
    """The control: a cached run."""
    usage = _normalize_usage({
        "input_tokens": 100,
        "output_tokens": 10,
        "cache_read_input_tokens": 400,
    })
    summary = cache_summary(usage)
    assert summary["prompt_cache_hit_tokens"] == 400, summary
    assert summary["cache_hit_rate"] == 0.8, summary


def test_the_aggregate_of_partial_turns_is_still_honest() -> None:
    """Combining turns must not invent a rate either."""
    summary = aggregate_cache_summary([
        {"prompt_cache_hit_tokens": 100},
        {"prompt_cache_hit_tokens": 100},
    ])
    assert summary["cache_hit_rate"] is None, (
        f"the aggregate invented a rate from half the counters: {summary}"
    )
    assert summary["prompt_cache_hit_tokens"] == 200, summary
