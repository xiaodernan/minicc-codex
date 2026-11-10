"""M8-T763 — ``minicc/logging_setup.py`` 的确定性契约。

这个模块是"日志只许去 stderr、密钥必须脱敏"的唯一家。单测钉住三件事：

1. ``resolve_level`` 的宽松输入处理（大小写不敏感、数字夹到 0-50、
   垃圾回退 WARNING）；
2. ``register_secret`` + ``redact`` 的注册值脱敏，以及
   ``[REDACTED:...]`` 标记不被二次脱敏（长度不增长）；
3. ``describe_event`` 的稳定 ``key=value`` 形状与 summary 截断。
"""

from __future__ import annotations

import logging

import pytest

from minicc import logging_setup as ls

_SECRET = "test-log-secret-unique-value-9f3a7b21"


def test_resolve_level_defaults_to_warning():
    assert ls.resolve_level("") == logging.WARNING
    assert ls.resolve_level("garbage") == logging.WARNING


def test_resolve_level_is_case_insensitive():
    assert ls.resolve_level("debug") == logging.DEBUG
    assert ls.resolve_level("INFO") == logging.INFO


def test_resolve_level_clamps_numeric_input():
    assert ls.resolve_level("0") == 0
    assert ls.resolve_level("999") == 50
    assert ls.resolve_level("15") == 15


def test_registered_secret_is_masked_everywhere():
    ls.register_secret(_SECRET)
    out = ls.redact(f"call failed with {_SECRET} on line 1")
    assert _SECRET not in out


def test_registered_secret_word_shaped_only_stands_alone():
    # 注册的 word-shaped 值（字母数字）只在独立位置被掩码，不吞进标识符
    ls.register_secret("testlogtoken")
    out = ls.redact("identifier testlogtokenx is fine, testlogtoken is not")
    assert out == "identifier testlogtokenx is fine, [REDACTED:credential] is not"


def test_already_redacted_marker_is_not_grown():
    text = "[REDACTED:credential]"
    out = ls.redact(text)
    assert out == text


def test_redact_tolerates_empty_and_none_like_input():
    assert ls.redact("") == ""


def test_describe_event_shape_and_unknowns():
    out = ls.describe_event({"kind": "task_start", "status": "ok"})
    assert "kind=task_start" in out
    assert "status=ok" in out
    assert "code=-" in out


def test_describe_event_only_allowlisted_detail_keys():
    out = ls.describe_event(
        {
            "kind": "task_end",
            "detail": {"turn": 3, "attempt": 2, "retry": 1, "tool_count": 7, "not_in_list": "zzz"},
        }
    )
    for key in ("turn=3", "attempt=2", "retry=1", "tool_count=7"):
        assert key in out
    assert "not_in_list" not in out


def test_describe_event_truncates_summary_to_200_chars():
    long_summary = "x" * 500
    out = ls.describe_event({"kind": "task_end", "summary": long_summary})
    # summary= 与 repr 包裹在内最多 ~203 字符可见形式
    assert out.count("x") <= 205


def test_describe_event_tolerates_non_mapping_event():
    out = ls.describe_event(None)
    assert out.startswith("kind=unknown")
