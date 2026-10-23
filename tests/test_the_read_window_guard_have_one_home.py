"""The read window guard must have exactly one home."""

from __future__ import annotations

import ast
import pathlib

import pytest

from minicc.tools.editor import EditError, _validate_read_window

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_home_accepts_a_valid_window():
    _validate_read_window(1, 10)


def test_home_rejects_offset_below_one():
    with pytest.raises(EditError, match="offset 必须 ≥ 1"):
        _validate_read_window(0, 10)
    with pytest.raises(EditError, match="offset 必须 ≥ 1"):
        _validate_read_window(-5, 10)


def test_home_rejects_limit_past_the_cap():
    with pytest.raises(EditError, match="超过单次读取上限"):
        _validate_read_window(1, 10**9)


def test_census_exactly_one_message_pair_and_it_is_the_home():
    source = (REPO / "minicc" / "tools" / "editor.py").read_text(encoding="utf-8")
    assert source.count("offset 必须 ≥ 1 (收到 {offset})") == 1
    assert source.count("超过单次读取上限") == 1
    lines = source.splitlines()
    first = next(i for i, line in enumerate(lines) if "offset 必须 ≥ 1" in line)
    window = "\n".join(lines[max(0, first - 14):first + 3])
    assert "def _validate_read_window" in window, window


def test_call_sites_use_the_home():
    source = (REPO / "minicc" / "tools" / "editor.py").read_text(encoding="utf-8")
    assert source.count("_validate_read_window(") == 3
    hits = []
    for path in sorted((REPO / "minicc").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "offset 必须" in line:
                hits.append((path.relative_to(REPO).as_posix(), lineno))
    assert len(hits) == 1, hits
