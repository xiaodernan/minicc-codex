"""M8-T773 — 两个半独立小模块：const-guard / stdout writer。

`minicc/input_guard.py::require_text` 是十处曾经手抄"字段不能为空"的唯一家
（JSON 入口的两半：isinstance 挡住 JSON 数字、strip 挡住全空白）。
`minicc/cli_io.py` 是 minicc 里唯一的 stdout 写出口（M8-T5）。
两个模块零同名测试（模块→测试映射发现）。
"""

from __future__ import annotations

import io
import sys

import pytest

from minicc import cli_io, input_guard


# ---------- input_guard ----------

def test_require_text_strips_and_returns():
    assert input_guard.require_text("  hello  ", "name") == "hello"


def test_require_text_rejects_blank_whitespace():
    with pytest.raises(ValueError):
        input_guard.require_text("   ", "name")


def test_require_text_rejects_missing_and_non_string():
    with pytest.raises(ValueError):
        input_guard.require_text(None, "name")
    with pytest.raises(ValueError):
        input_guard.require_text(42, "name")  # JSON 数字绝不许变成会话 id
    with pytest.raises(ValueError):
        input_guard.require_text(["x"], "name")


def test_require_text_error_names_the_field():
    with pytest.raises(ValueError, match="session_id"):
        input_guard.require_text(None, "session_id")


# ---------- cli_io ----------

def test_cli_out_writes_default_sep_and_end(capsys):
    cli_io.cli_out("hello", "world")
    captured = capsys.readouterr()
    assert captured.out == "hello world\n"
    assert captured.err == ""


def test_cli_out_honors_sep_and_end(capsys):
    cli_io.cli_out("a", "b", "c", sep="|", end="")
    captured = capsys.readouterr()
    assert captured.out == "a|b|c"


def test_cli_out_can_target_another_file(tmp_path, capsys):
    out = tmp_path / "out.txt"
    with open(out, "w", encoding="utf-8") as fh:
        cli_io.cli_out("to file", file=fh)
    assert out.read_text(encoding="utf-8") == "to file\n"
    assert capsys.readouterr().out == ""
