"""Gate for the reader that resolves 「第N节」 against the section the citation lives under.

Two defects are stacked here, and the first one is not the interesting one.

**入口** - ``_SECTION`` admitted no space beside the number, so ``见第 6 节``, which is how
this repository ships its records, was not a locator at all. Measured over the corpus before
the change: 24 live section citations sat in ``citation-without-locator``, counted and never
adjudicated.

**口径** - the roster they would have resolved against, ``_numbered_headings``, keeps only
*level-2* headings, and in ``docs/ROADMAP_TO_PRODUCT.md`` the only numbered level-2 headings
are the seven front-matter sections (``## 一、结论先行`` … ``## 七、面试讲解要点``). Every
batch's own ``### 6 真发现：…`` and ``### 8 基线…`` is level-3 and was in no table at all -
2067 headings, none of them pointable. So fixing the entrance alone ties 24 real pointers to
answers of a different question: 「第 6 节」 written inside batch 445 would land on
``## 六、每个阶段应该跟踪的指标``, exist, and go green. Measured: 22 of the 24 mis-aimed
greens plus 2 false reds (「第 8 节」 is declared *only* as a batch's own ``### 8``), which is
the trade this file exists to make impossible.

Resolution is therefore nearest-first: the batch a citation sits inside owns the number, the
document-wide table is the fallback, and a citation whose number nothing declares stays red.
The one honest limit of that rule is the reverse reading - an author who means a front-matter
section while writing inside a batch that also numbers that section silently gets the local
one; the corpus holds 0 such citations today, and S2 below is what would catch it appearing.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "doc_pointers.py"


def _load(name: str = "minicc_doc_pointers_section_scope") -> object:
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # scripts/ is not a package; the dataclasses inside resolve annotations through
    # sys.modules, so the module must be registered before it executes.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


dp = _load()

#: The census is written here, not borrowed from the reader: a gate that asks the reader
#: "what do you see?" with the reader's own pattern can only ever agree with it, and that is
#: how 24 citations spent a hundred batches in the box that promises nothing. It spells the
#: numeral class ``_NUM`` spells (the 节 axis never needed 百/千) and every Unicode blank on
#: either side of it.
_CN = "零一二三四五六七八九十"
_ANY_SECTION_CITATION = re.compile(rf"第\s*(?:\d+|[{_CN}]+)\s*节")


def _reported(text: str) -> tuple[list[str], int, dict[str, int]]:
    problems, checked, boxes = dp.check_pointers(Path("synthetic.md"), text)
    assert checked or sum(boxes.values()), "标记一个都没 harvest 到，这条门就是空的"
    return [p.detail for p in problems], checked, boxes


def _front_matter_and_a_batch() -> str:
    """The corpus shape, small: seven numbered level-2 sections, then batches whose own
    ``### N`` sub-items are the sections the prose inside them means."""
    return (
        "# T\n\n"
        "## 三、里程碑总表\n\n"
        "卷首的表在卷首。\n\n"
        "## 第四百零一批 M8-T901 一个批次\n\n"
        "### 8 本批的下一批候选\n\n"
        "结论见第 8 节。\n"
    )


def test_a_citation_to_a_number_only_the_batch_declares_is_answered_by_that_batch() -> None:
    """「第 8 节」 inside a batch: the batch declares 8, the front matter does not.

    Before the change this sentence was not adjudicated at all - the space beside the number
    made it a locator-shaped nothing, and it landed in ``citation-without-locator``.
    """
    text = _front_matter_and_a_batch()
    problems, checked, boxes = _reported(text)
    assert boxes[dp.BOX_CHECKED] == 1 and checked == 1, boxes
    assert problems == [], problems


def test_the_batch_section_shadows_the_front_matter_for_the_same_number() -> None:
    """The false green: 3 is declared by ``## 三、里程碑总表`` *and* by this batch's
    ``### 3``, and the citation is written inside the batch, under its heading.

    The verdict is green either way, so counting problems cannot see which target answered.
    The witness is an id the citation *itself* claims, carried inside the quoted span, and
    declared by a table row in the batch's own subsection: the reader adjudicates id claims
    against the body of whichever section it resolved to, and it counts only structural
    positions (headings, row label cells) as declaring one. So the same citation is green on
    the local answer and reports ``「第3节 M8-T903」 说 M8-T903 在「三、里程碑总表」里`` on the
    front-matter one - which is what makes this the precedence case, and the only one.
    """
    text = (
        "# T\n\n"
        "## 三、里程碑总表\n\n"
        "卷首的表在卷首，这里没有那个编号。\n\n"
        "## 第四百零二批 M8-T902 一个批次\n\n"
        "### 3 本批的判定表\n\n"
        "| M8-T903 | 本批在这张表里立的编号 |\n\n"
        "结论见「第3节 M8-T903」。\n"
    )
    problems, checked, _boxes = _reported(text)
    assert checked == 1, checked
    assert problems == [], problems
    tables = dp._subsection_tables(dp.sections(text))
    assert 3 in tables[0][1], f"本批的 ### 3 没进体内表：{tables}"
    assert tables[0][1][3].title.startswith("3 本批的判定表"), tables
    assert dp._numbered_headings(dp.sections(text))[3].title == "三、里程碑总表"


def test_a_number_the_batch_does_not_declare_still_answers_the_document_table() -> None:
    """Nearest-first must not *narrow* what a citation can reach: this batch numbers only
    ``### 3``, so 第5节 has no local answer and takes the document-wide section, as it did
    before this batch existed."""
    text = (
        "# T\n\n"
        "## 五、每个阶段跟踪的指标\n\n"
        "指标在卷首第五节。\n\n"
        "## 第四百零三批 M8-T904 一个批次\n\n"
        "### 3 本批的判定表\n\n"
        "结论见「第5节」。\n"
    )
    problems, checked, _boxes = _reported(text)
    assert checked == 1, checked
    assert problems == [], problems


def test_a_citation_to_a_number_no_table_declares_stays_red() -> None:
    """The red path keeps its teeth, and keeps its sentence: the citation is unspaced, so it
    was already adjudicated before this batch, and it is still a finding."""
    text = (
        "# T\n\n"
        "## 三、里程碑总表\n\n"
        "## 第四百零四批 M8-T905 一个批次\n\n"
        "### 3 本批的判定表\n\n"
        "结论见「第9节」。\n"
    )
    problems, checked, _boxes = _reported(text)
    assert checked == 1, checked
    assert len(problems) == 1, problems
    assert "第9节" in problems[0] and "不存在" in problems[0], problems[0]


def test_a_space_on_either_side_of_the_number_is_the_same_citation() -> None:
    """Both spellings are shipped, and neither may buy its way out of the adjudicated
    account.

    The front matter declares 六 here on purpose: this case is about *visibility*, so the
    number must stay answerable even if the batch table goes blind. Which of the two
    sections answers is S2's business, not this one's.
    """
    text = (
        "# T\n\n"
        "## 六、每个阶段跟踪的指标\n\n"
        "指标在卷首第六节。\n\n"
        "## 第四百零五批 M8-T906 一个批次\n\n"
        "### 6 本批的基线\n\n"
        "结论见「第6节」，另见「第 6 节」。\n"
    )
    problems, checked, boxes = _reported(text)
    assert checked == boxes[dp.BOX_CHECKED] == 2, boxes
    assert problems == [], problems
    boxes_only = [box for _o, _s, box, _t in dp._pointer_spans(text)]
    assert boxes_only.count(dp.BOX_CHECKED) == 2, boxes_only


def test_the_first_numbered_subsection_wins_the_key_when_a_batch_declares_two() -> None:
    """Two ``### 3`` headings inside one batch are a real thing in this corpus, so the table
    needs the same first-wins rule ``_numbered_headings`` and ``_id_registry`` already apply -
    otherwise document order silently decides the target at the *later* duplicate."""
    text = (
        "# T\n\n"
        "## 三、里程碑总表\n\n"
        "## 第四百零七批 M8-T908 一个批次\n\n"
        "### 3 甲：编号在这里\n\n"
        "| M8-T909 | 第一处声明的编号 |\n\n"
        "### 3 乙：同号的第二处\n\n"
        "结论见「第3节 M8-T909」。\n"
    )
    problems, checked, _boxes = _reported(text)
    assert checked == 1, checked
    assert problems == [], problems
    tables = dp._subsection_tables(dp.sections(text))
    assert len(tables) == 1, tables
    assert 3 in tables[0][1], f"体内表里没有 3 这个号：{tables}"
    first = tables[0][1][3]
    assert first.title == "3 甲：编号在这里", first
    assert first.line == 7, first
    assert [s.title for s in dp.sections(text) if s.title.startswith("3 ")][1] == "3 乙：同号的第二处"


def test_a_wide_space_between_the_particle_and_the_number_is_the_same_citation() -> None:
    """What ``\\s`` actually decides here, pinned on a blank the corpus does not use yet.

    The harvest grammar (``_POINTER``, shipped) stops the captured span at a newline, so a
    citation wrapped across two lines never reaches this locator test at all - the newline
    half of ``\\s*`` is unreachable from the reader's own entrance, and saying so in a gate
    would pin the wrapper bug rather than the spacing rule. An ideographic space is the
    reachable one, and it is the same citation.
    """
    text = (
        "# T\n\n"
        "## 第四百零八批 M8-T910 一个批次\n\n"
        "### 6 本批的基线\n\n"
        "结论见第　6　节。\n"
    )
    problems, checked, boxes = _reported(text)
    assert boxes[dp.BOX_CHECKED] == 1 and checked == 1, boxes
    assert problems == [], problems


def test_the_relaxed_declaration_shape_moves_no_document_level_section_key() -> None:
    """The widening is paid for with evidence, not with preference.

    ``_DECLARED_NUMBER`` now accepts a bare space after the numeral where the shipped rule
    demanded ``.`` or ``、``. That single rule feeds both tables, which is the point, and it
    also feeds the *document-wide* table for the first time — so the claim this batch must
    prove, before asking a later reader to trust it, is that nothing that used to resolve
    still resolves somewhere else. Measured over the corpus with the old rule re-spelled here
    (the gate does not borrow the reader's pattern), the two tables are one table: same keys,
    same target lines. ``## 2026-09-25：…`` stays out of both, because a number followed by a
    hyphen has no separator at all.
    """
    def strict_table(headings: list[dp.Section]) -> dict[int, tuple[int, str]]:
        out: dict[int, tuple[int, str]] = {}
        for section in headings:
            if section.level != 2:
                continue
            match = re.match(r"^([一二三四五六七八九十]+|\d+)[.、]", section.title)
            if match:
                numeral = dp._numeral(match.group(1))
                if numeral is not None:
                    out.setdefault(numeral, (section.line, section.title))
        return out

    relaxed_total = 0
    for document in dp.DEFAULT_DOCS:
        text = document.read_text(encoding="utf-8")
        headings = dp.sections(text)
        relaxed = {
            numeral: (section.line, section.title)
            for numeral, section in dp._numbered_headings(headings).items()
        }
        assert relaxed == strict_table(headings), (
            f"{document.name}：放宽声明形状挪动了文档级编号表，"
            f"旧读法 {sorted(strict_table(headings))} 新读法 {sorted(relaxed)}"
        )
        relaxed_total += len(relaxed)
    assert relaxed_total >= 7, f"整个语料没有一条文档级编号标题可比：{relaxed_total}"


def test_the_corpus_adjudicates_every_section_citation_it_holds() -> None:
    """The change is measured on the document that made it, with a census the reader does not
    own, and every clause derived rather than hand-typed.

    Two things must both stay true: no section citation may sit in a box nothing adjudicates
    (that was 24 lines), and making them decidable must not manufacture a red - they name
    sections that exist, so the only honest outcome is a verdict, not a false finding. The
    floor sits under today's 30 rather than at it; it catches the failure this batch is about,
    where a narrowing of the numeral class or of the spacing sends citations back into the
    open account.
    """
    unchecked: list[tuple[str, int, str, str]] = []
    reds: list[tuple[str, int, str]] = []
    census = 0
    for document in dp.DEFAULT_DOCS:
        text = document.read_text(encoding="utf-8")
        problems, _checked, _boxes = dp.check_pointers(document, text)
        for problem in problems:
            if problem.kind == "POINTER" and _ANY_SECTION_CITATION.search(problem.detail):
                reds.append((document.name, problem.line, problem.detail[:70]))
        for offset, span, box, _targets in dp._pointer_spans(text):
            if _ANY_SECTION_CITATION.search(span) is None:
                continue
            census += 1
            if box != dp.BOX_CHECKED:
                unchecked.append((document.name, dp._line_of(text, offset), box, span[:48]))
    assert unchecked == [], f"节引用仍落在没人裁决的箱子里：{unchecked}"
    assert reds == [], f"节引用被判成指向不存在，而编号就在标题里：{reds}"
    assert census >= 20, f"普查只收到 {census} 条节引用：读者又开始看不见带空格的编号"
