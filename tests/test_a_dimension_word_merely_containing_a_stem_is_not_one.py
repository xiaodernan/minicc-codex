"""M8-T316 — 维度关键词也要**词边界**

M8-T290 已经给 `_CONNECTOR_RE` 补过词边界（"understand" 里的 "and" 不是连接词），
而**同一类缺陷原样留在** `dimensions` 里：那些英文选项全是**无边界子串**。

于是**一个词点亮两个维度**：

| 词 | 命中的维度 |
| --- | --- |
| `latest` | verification（含 `test`）+ research |
| `web` | research + presentation |
| `address` | implementation（含 `add`） |
| `prefix` | implementation（含 `fix`） |

实测的代价：一个"更新发布说明、顺便提一句 changelog"的请求匹配到**四个**维度 →
分数越过阈值 → 规划器把它拆成**两个只读子任务**——一件改文案的事被分成了
调研。

本门禁钉住：包含不算命中；变形词仍然算命中。
"""

from __future__ import annotations

import re

import pytest

from minicc.agent.orchestration import DIMENSION_PATTERNS, assess_complexity


def _dimensions(text: str) -> set[str]:
    """The dimensions a text matches, read through the same table."""
    return {
        name
        for name, pattern in DIMENSION_PATTERNS.items()
        if re.search(pattern, text, re.I)
    }


def test_a_word_that_merely_contains_a_stem_is_not_a_dimension() -> None:
    """``latest`` is not a test; ``address`` is not an add."""
    matched = _dimensions("update the release notes for the latest build")
    assert "verification" not in matched, (
        f"'latest' lit up the verification dimension: {matched}"
    )

    address = _dimensions("update the address book")
    assert "implementation" not in address, (
        f"'address' lit up the implementation dimension: {address}"
    )


def test_a_dimension_that_came_from_a_substring_no_longer_counts() -> None:
    """The observable consequence: one word, one dimension.

    ``the latest release`` used to be two dimensions (research + verification)
    because ``latest`` contains ``test`` - so a single mention of a
    release note looked like a research task *and* a testing task.
    """
    before = _dimensions("the latest release")
    assert "verification" not in before, before
    assert "research" in before, before
    assert len(before) == 1, before


def test_the_real_words_still_match() -> None:
    """The control: the ordinary words are unchanged."""
    matched = _dimensions("please fix the bug and add a test")
    assert "implementation" in matched, matched
    assert "verification" in matched, matched


def test_inflections_still_match() -> None:
    """A word boundary must not cost the inflections."""
    matched = _dimensions("we are migrating the service and validating the result")
    assert "implementation" in matched, matched
    assert "verification" in matched, matched


def test_the_chinese_words_are_unchanged() -> None:
    """The control: the Chinese alternatives are untouched."""
    matched = _dimensions("请修复解析器并补上测试")
    assert "implementation" in matched, matched
    assert "verification" in matched, matched
