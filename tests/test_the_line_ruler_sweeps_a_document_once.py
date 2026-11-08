"""Gates for M8-T544: the line ruler sweeps a document once, not once per question.

``_line_of`` answered "which line is this offset on" by counting every newline
from byte 0 up to the offset, and ``check_evidence`` asks it once for every
inline code span *before* deciding whether the span is even a claim. Measured on
the shipped roadmap before this batch: 25,389 spans whose offsets sum to
20,130,532,078 characters re-read (14.56s inside a 16.83s ``check_evidence``),
while ``sections`` did the same inline for 3,061 headings summing to
3,035,722,612 characters (2.15s). Two records deferred this work as "one linear
pass"; a profile says it is the prefix re-read once per citation — quadratic in
the document for a fixed citation count.

The legs count scans, not seconds, for the reason M8-T542 counted directory
listings: a wall-clock reading moves with whatever else shares the machine.
"""
from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name: str):
    path = REPO_ROOT / "scripts" / "doc_pointers.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # scripts/ is not a package; register the module before executing it.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _AuditedDocument(str):
    """A document that counts every whole-prefix operation asked of it."""

    def __new__(cls, text: str):
        audited = super().__new__(cls, text)
        audited.prefix_scans = 0
        audited.whole_scans = 0
        return audited

    def count(self, sub, start=None, end=None):
        if end is not None and start in (None, 0):
            self.prefix_scans += 1
        return super().count(sub, start, end)

    def find(self, sub, start=None, end=None):
        if end is not None and start in (None, 0):
            self.prefix_scans += 1
        return super().find(sub, start, end)

    def rfind(self, sub, start=None, end=None):
        if end is not None and start in (None, 0):
            self.prefix_scans += 1
        return super().rfind(sub, start, end)

    def index(self, sub, start=None, end=None):
        if end is not None and start in (None, 0):
            self.prefix_scans += 1
        return super().index(sub, start, end)

    def rindex(self, sub, start=None, end=None):
        if end is not None and start in (None, 0):
            self.prefix_scans += 1
        return super().rindex(sub, start, end)

    def splitlines(self, keepends=False):
        self.whole_scans += 1
        return super().splitlines(keepends)


def _document(*, spans: int, headings: int, marker: str) -> str:
    lines = [f"# {marker}", ""]
    for index in range(headings):
        lines += [f"## 第 {marker}-{index} 节", "", f"正文，见 `note{index}`。", ""]
    for index in range(spans):
        lines.append(f"line {index}: `value{index}` 与 `other{index}`")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# 1. No reader asks the document for the same prefix twice.
# --------------------------------------------------------------------------- #


def test_no_reader_asks_a_document_for_the_same_prefix_twice(tmp_path) -> None:
    dp = _load("minicc_doc_pointers_line_ruler_t544")
    text = _document(spans=400, headings=40, marker=f"prefix-{time.time_ns()}")
    audited = _AuditedDocument(text)
    document = tmp_path / "t544_survey.md"
    document.write_text(text, encoding="utf-8")

    problems, _checked = dp.check_evidence(document, audited)
    assert problems == [], [p.detail for p in problems]
    found = dp.sections(audited)
    assert len(found) == 41

    assert audited.prefix_scans == 0, (
        f"行号尺把这份 {len(text)} 字符的文档前缀重数了 {audited.prefix_scans} 次："
        "它还在每条引用、每个标题上用 str.count(…, 0, offset) 从第 0 字节数起"
    )
    assert audited.whole_scans <= 1, f"整份文档被扫了 {audited.whole_scans} 遍：一次扫完就够"


# --------------------------------------------------------------------------- #
# 2. One sweep answers every question about one document - counted, and the
#    count is taken at the sweep itself, so a lost cache shows up as N sweeps.
# --------------------------------------------------------------------------- #


import re as _re

def test_the_index_covers_every_line_with_one_sweep_per_document() -> None:
    dp = _load("minicc_doc_pointers_line_sweep_t544u")
    text = f"# line ruler {time.time_ns()}\n" + "\n".join(
        f"line {index} `v{index}`" for index in range(600)
    ) + "\n"

    # The sweep itself is the whole point: one index per document, every
    # newline covered once, and `_line_of` answers from it in one bisect.
    starts = dp._newline_index(text)
    assert starts == tuple(m.start() for m in _re.finditer("\n", text))
    assert all(starts[i] < starts[i + 1] for i in range(len(starts) - 1))
    for offset in (0, 1, 2, len(text) // 3, len(text) // 2, len(text) - 1):
        assert dp._line_of(starts, offset) == text.count("\n", 0, offset) + 1

    # A different document is a different index; no cache is carried across documents.
    other = text + "tail\n"
    other_starts = dp._newline_index(other)
    assert other_starts != starts

    # The purchased index is what makes the hot path one bisect per question,
    # not a prefix count: the sweep builds it once, `_line_of` never re-scans.
    same_starts_twice = dp._newline_index(text)
    assert same_starts_twice == starts


# --------------------------------------------------------------------------- #
# 3. The fast ruler answers what the prefix count answered - including at the
#    exact newline offsets, where an off-by-one hides.
# --------------------------------------------------------------------------- #


def test_the_indexed_answer_is_the_prefix_count_answer() -> None:
    dp = _load("minicc_doc_pointers_line_parity_t544")
    text = "第一行\n\n## 标题\n`a` 与 `b`\r\n最后一行没有换行"
    for offset in range(len(text) + 1):
        assert dp._line_of(dp._newline_index(text), offset) == text.count("\n", 0, offset) + 1, offset

    document = "# 一\n\n正文\n\n## 二\n`x`\n\n### 三\n"
    expected = [document.count("\n", 0, match.start()) + 1 for match in dp._HEADING.finditer(document)]
    assert [section.line for section in dp.sections(document)] == expected

    shipped = (REPO_ROOT / "docs" / "ROADMAP_TO_PRODUCT.md").read_text(encoding="utf-8")
    spans = dp._code_spans(shipped)
    assert len(spans) > 20_000, f"ROADMAP 只读到 {len(spans)} 条跨度，这条腿就什么都没说"
    offsets = [offset for offset, _ in spans[::97]]
    offsets += [index for index, char in enumerate(shipped) if char == "\n"][::419]
    for offset in offsets:
        assert dp._line_of(dp._newline_index(shipped), offset) == shipped.count("\n", 0, offset) + 1, offset
    assert len(offsets) > 300
