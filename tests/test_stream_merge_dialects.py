"""M8-T764 — ``minicc/llm/stream_merge.py`` 的方言契约。

这个模块是流式文本组装的唯一家，零同名测试（模块→测试映射发现）。它的
关键承诺在 docstring 里说得很清楚，单测把它们钉成回归门：

1. 同一 attempt 内增量 byte-for-byte 追加（"7." + "7.7" → "7.7.7"，P0-1 案）；
2. 只有连续两段（CUMULATIVE_STREAK）整前缀重复 + 增长，才把流重解释为
   累积快照——单次重复绝不截断；
3. 重解释那一 feed 的 ``latched_now`` 置位；之后每个快照是真值；
4. 重试合并 `merge_retry_snapshot` 的四种重叠形状。
"""

from __future__ import annotations

import pytest

from minicc.llm import stream_merge as sm


# ---------- append_delta ----------

def test_append_delta_into_empty_previous():
    assert sm.append_delta("", "hello") == ("hello", "hello")


def test_append_delta_concatenates_byte_for_byte():
    assert sm.append_delta("ab", "c") == ("abc", "c")


def test_append_delta_empty_fragment_is_noop():
    assert sm.append_delta("ab", "") == ("ab", "")


# ---------- CUMULATIVE_STREAK ----------

def test_cumulative_streak_is_two():
    assert sm.CUMULATIVE_STREAK == 2


# ---------- AttemptTextAssembler：增量方言 ----------

def test_incremental_stream_appends_byte_for_byte():
    asm = sm.AttemptTextAssembler()
    for fragment in ["hel", "lo", " ", "wo", "rld"]:
        emitted = asm.feed(fragment)
    assert asm.text == "hello world"
    assert asm.cumulative is False
    assert asm.latched_now is False


def test_single_repeat_is_not_reinterpreted_the_fable_from_the_docstring():
    # P0-1 / 7.7.7 案："7." 后 "7.7" 只被增量追加，不被去重
    asm = sm.AttemptTextAssembler()
    asm.feed("7.")
    asm.feed("7.7")
    assert asm.text == "7.7.7"
    assert asm.cumulative is False


# ---------- AttemptTextAssembler：累积快照方言 ----------

def test_snapshot_stream_is_reinterpreted_after_the_streak():
    asm = sm.AttemptTextAssembler()
    asm.feed("aa")       # streak=1（grows on previous=""），不计
    asm.feed("aab")      # streak=1
    emitted = asm.feed("aabc")  # streak=2 → 重解释
    assert asm.cumulative is True
    assert asm.latched_now is True
    assert emitted == "aabc"
    assert asm.text == "aabc"


def test_latched_now_only_on_the_reinterpreting_feed():
    asm = sm.AttemptTextAssembler()
    asm.feed("aa")
    asm.feed("aab")
    assert asm.latched_now is False
    asm.feed("aabc")
    assert asm.latched_now is True
    asm.feed("aabcd")
    assert asm.latched_now is False


def test_cumulative_snapshots_from_then_on_are_treated_as_truth():
    asm = sm.AttemptTextAssembler()
    asm.feed("aa")
    asm.feed("aab")
    asm.feed("aabc")
    asm.feed("aabcXYZ")  # 整前缀快照，直接替换
    assert asm.text == "aabcXYZ"


# ---------- merge_retry_snapshot ----------

def test_merge_no_previous():
    assert sm.merge_retry_snapshot("", "abc") == ("abc", "abc")


def test_merge_no_current():
    assert sm.merge_retry_snapshot("abc", "") == ("abc", "")


def test_merge_current_extends_previous():
    assert sm.merge_retry_snapshot("abc", "abcdef") == ("abcdef", "def")


def test_merge_previous_covers_current():
    assert sm.merge_retry_snapshot("abcdef", "abc") == ("abcdef", "")


def test_merge_overlap_in_the_middle():
    # previous 尾 = current 头 的最大重叠去重
    assert sm.merge_retry_snapshot("abc123", "123xyz") == ("abc123xyz", "xyz")


def test_merge_no_overlap_appends():
    assert sm.merge_retry_snapshot("abc", "xyz") == ("abcxyz", "xyz")
