"""Gate for the reader that resolves 「第N批」 cross-references at or past one hundred.

The defect is arithmetic. ``_NUM`` spells a number as ``\\d+`` or a run of
``一二三四五六七八九十``, so the first batch number it cannot read is 100 — and this
project is past batch 364. Measured over the shipped corpus before the change
(``docs/ROADMAP_TO_PRODUCT.md``, 2097 headings): the roster held **102** batch labels
while the document declares **363**, and 9 live 「见」markers naming a batch at or past
100 were filed in ``citation-without-locator``. That box is an honest apology, not a lie
— nothing here produced a false green — but it is a promise that no later reader will ever
collect: a pointer to a batch that does not exist would be counted, never adjudicated, and
every pointer written from now on names an unreadable number.

Widening the numeral class alone is not the fix, and half of this file exists to say why.
The roster used to run the matcher over the *whole title*, so admitting a space would also
have admitted ``## 4 顺手关掉第 91 批 §8 第 3 条的恐怖半边`` — a sub-item inside batch 203
that mentions 91 — as the owner of the key 「第91批」. That converts a false RED (the arabic
spelling resolved to nothing) into a false GREEN (it resolves to the wrong section, and
``setdefault`` lets document order decide in the twelve other cases where a real heading
also exists). So the labels now come from declaration positions only, which is the same
doctrine ``_id_registry`` already applies to ids.

The 节 axis is deliberately untouched: measured, admitting 百/千 there changes 0 verdicts
(162 matches, 13 distinct numbers, before and after) because no section is numbered past 99.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "doc_pointers.py"


def _load(name: str = "minicc_doc_pointers_t379") -> object:
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # scripts/ is not a package; the dataclasses inside resolve annotations through
    # sys.modules, so the module must be registered before it executes.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


dp = _load()

#: The census this file reads pointers with is written here, on purpose: a gate that
#: borrows the reader's own pattern can only ever agree with it, which is how a reader
#: that sees 102 of 363 labels stayed green for two hundred batches.
_CN = "零一二三四五六七八九十百千两"
_ANY_BATCH_LABEL = re.compile(rf"第\s*(?:\d+|[{_CN}]+)\s*批(续二|续)?")


def _reported(text: str) -> tuple[list[str], int, dict[str, int]]:
    problems, checked, boxes = dp.check_pointers(Path("synthetic.md"), text)
    assert checked or sum(boxes.values()), "标记一个都没 harvest 到，这条门就是空的"
    return [p.detail for p in problems], checked, boxes


def test_a_batch_number_at_or_past_one_hundred_is_a_locator_and_its_heading_answers_it() -> None:
    """「见「第二百二十批」」 is a pointer, and a heading owns it. The same sentence at
    第五十七批 was adjudicated; the only difference is the number of digits the reader
    can spell."""
    text = "# T\n\n## 第二百二十批 M8-T9：某件事\n\n结论见「第二百二十批」。\n"
    problems, checked, boxes = _reported(text)
    assert problems == [], problems
    assert checked == boxes[dp.BOX_CHECKED] == 1, boxes


def test_a_pointer_to_an_unexisting_batch_past_one_hundred_is_red() -> None:
    """The teeth: this is the verdict the open account could never have produced.

    Before the change the sentence below was not a finding at all — the marker landed in
    ``citation-without-locator``, which is counted and stays open. A reader that cannot
    spell the number cannot catch a wrong number either.
    """
    text = "# T\n\n## 第二百二十批 甲\n\n结论见「第四百批」。\n"
    problems, checked, _boxes = _reported(text)
    assert checked == 1, "这条指针没有进受检箱，就没人裁决它"
    assert len(problems) == 1, problems
    assert "第四百批" in problems[0] and "不存在" in problems[0], problems[0]


def test_spaces_around_the_number_are_the_same_label_on_both_sides() -> None:
    """``## 第 203 批 …`` is a heading this repository shipped, in prose that writes
    「第203批」 without the spaces. One key builder, fed by match groups rather than match
    text, is what makes the two spellings one label in both directions."""
    spaced_title = "# T\n\n## 第 203 批 M8-T176\n\n结论见「第203批」。\n"
    problems, checked, _boxes = _reported(spaced_title)
    assert problems == [] and checked == 1, (problems, checked)
    spaced_pointer = "# T\n\n## 第203批 M8-T176\n\n结论见「第 203 批」。\n"
    problems, checked, _boxes = _reported(spaced_pointer)
    assert problems == [] and checked == 1, (problems, checked)


def test_two_spellings_of_one_number_stay_two_labels() -> None:
    """「第两百二十批」 and 「第二百二十批」 are two shipped headings 45 lines apart, so a
    key canonicalised by arithmetic would let one pointer answer for both. The number is
    read for *shape*, never evaluated: two spellings means two labels, and a heading that
    uses one does not satisfy a pointer that uses the other."""
    both = "# T\n\n## 第两百二十批 甲\n\n## 第二百二十批 乙\n\n结论见「第二百二十批」。\n"
    problems, checked, _boxes = _reported(both)
    assert problems == [] and checked == 1, problems
    claims = dp._batch_claims(dp.sections(both))
    assert {"第两百二十批", "第二百二十批"} <= set(claims), sorted(claims)
    assert claims["第两百二十批"][0].line != claims["第二百二十批"][0].line, claims
    only_liang = "# T\n\n## 第两百二十批 甲\n\n结论见「第二百二十批」。\n"
    problems, checked, _boxes = _reported(only_liang)
    assert checked == 1 and len(problems) == 1, problems
    assert "第二百二十批" in problems[0], problems[0]


def test_a_heading_that_only_mentions_a_batch_does_not_own_its_label() -> None:
    """The false green the widening would have shipped on its own.

    ``## 4 顺手关掉第 91 批 §8 …`` is a numbered sub-item inside another batch talking *about*
    batch 91; the real section signs itself 「第九十一批」. Reading the mention into the roster
    hands 「第91批」 to the wrong body — and because the two spellings are two different dict
    keys, the correct heading cannot outvote it.
    """
    text = (
        "# T\n\n## 第九十一批 正文\n\n## 4 顺手关掉第 91 批 §8 的那半边\n\n"
        "结论见「第91批」，另见「第九十一批」。\n"
    )
    claims = dp._batch_claims(dp.sections(text))
    assert "第九十一批" in claims, sorted(claims)
    assert "第91批" not in claims, f"提到别的批次的标题认领了那个批号：{sorted(claims)}"
    problems, checked, _boxes = _reported(text)
    assert checked == 2, checked
    assert len(problems) == 1, problems
    assert "第91批" in problems[0] and "第九十一批" not in problems[0], problems[0]


def test_a_bracket_colophon_is_a_declaration() -> None:
    """``### M8 退出标准真跑记录（第十八批，2026-09-23）`` is how the early exit-criteria
    sections signed themselves, and 14 live corpus pointers already resolve through that
    shape. The rule may not narrow the roster to titles that open with their number."""
    text = "# T\n\n### M8 退出标准真跑记录（第七批，2026-09-23）\n\n结论见「第七批」。\n"
    problems, checked, _boxes = _reported(text)
    assert problems == [] and checked == 1, (problems, checked)
    claims = dp._batch_claims(dp.sections(text))
    assert claims["第七批"][0].line == 3, claims["第七批"]


def test_a_range_heading_does_not_lend_its_tail_number_to_the_roster() -> None:
    """``## 附：第三百三十五~六十五批…`` names a *span* of batches. The particle 「第」 is
    required on the pointer side and the colophon side exactly because dropping it would
    harvest 「第六十五批」 out of that tail and point every such citation at the appendix."""
    text = (
        "# T\n\n## 附：第三百三十五~六十五批总账\n\n"
        "结论见「第三百三十五批」，另见「第六十五批」。\n"
    )
    claims = dp._batch_claims(dp.sections(text))
    assert "第六十五批" not in claims, sorted(claims)
    assert "第三百三十五批" not in claims, sorted(claims)
    problems, _checked, _boxes = _reported(text)
    assert len(problems) == 2, problems
    assert all("不存在" in detail for detail in problems), problems


def test_the_corpus_files_no_batch_pointer_as_unresolvable() -> None:
    """The change has to be measured on the document that made it, with a census the
    reader does not own.

    Two clauses, both derived rather than counted: every 「见」 marker whose span carries a
    batch label of *any* spelling this file can spell sits in the checked box (the 9 that
    sat in ``citation-without-locator`` before are the reason), and none of them is then
    reported as pointing at nothing — they name real sections, so making them decidable
    must not manufacture a red. The roster floor sits under today's 363 rather than at it,
    because a floor at the current number reds on the next record and teaches nobody
    anything; it catches the failure this batch is about, where a narrowed numeral class
    collapses the roster back to the few labels below 100.
    """
    unchecked: list[tuple[str, int, str, str]] = []
    reds: list[tuple[str, int, str]] = []
    roster_total = 0
    for document in dp.DEFAULT_DOCS:
        text = document.read_text(encoding="utf-8")
        roster_total += len(dp._batch_claims(dp.sections(text)))
        problems, _checked, _boxes = dp.check_pointers(document, text)
        for problem in problems:
            if problem.kind == "POINTER" and _ANY_BATCH_LABEL.search(problem.detail):
                reds.append((document.name, problem.line, problem.detail[:70]))
        for offset, span, box, _targets in dp._pointer_spans(text):
            if _ANY_BATCH_LABEL.search(span) is None:
                continue
            if box != dp.BOX_CHECKED:
                unchecked.append((document.name, dp._line_of(text, offset), box, span[:48]))
    assert unchecked == [], f"批号指针仍落在没人裁决的箱子里：{unchecked}"
    assert reds == [], f"批号指针被判成指向不存在，而标题就在文档里：{reds}"
    assert roster_total >= 360, f"名册只剩 {roster_total} 个批号键：读者又开始看不见大于一百的批号"
