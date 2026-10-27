"""Gates for M8-T521: the evidence reader must read fences with the same ruler as the pointer reader.

Two readers walk the shipped documents. ``_mask_code`` decides which bytes are code before a *pointer* is
harvested; ``_code_spans`` decides which bytes are code before an *evidence* citation is judged. Through
M8-T520 those were two different rulers: the pointer reader was converted (M8-T519) to a line-anchored
state machine that treats a `` ``` `` run in the middle of a table cell as prose, while the evidence
reader still ran ```` ```.*?``` ````, a byte-pairing regex with no concept of a line.

Byte pairing is not "a slightly wider scope" — it is a **phase** lock over the whole file, so one prose
mention of a fence marker re-pairs every block after it. Measured on the shipped corpus before this
batch: 12 spans were harvested from *inside* closed blocks (a quotation charged as a claim), and the
ROADMAP row that writes an in-cell fence marker while naming ``test_every_doc_example_runs_verbatim``
swallowed the citations written on the same line. Leg 1 asserts both directions in the same text on
purpose: a gate that only measured "the reader now sees more" would have shipped the second defect.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "doc_pointers.py"


def _load(name: str = "minicc_doc_pointers_t521"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # scripts/ is not a package; @dataclass(slots=True) resolves annotations via
    # sys.modules, so register the module before executing it.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


dp = _load()
_ROADMAP = REPO_ROOT / "docs" / "ROADMAP_TO_PRODUCT.md"

#: ROADMAP L1550 writes a fence marker inside a table cell while describing
#: ``test_every_doc_example_runs_verbatim``. The two citations written on that same
#: line are the ones a *block-only* swap would throw away: the line-anchored ruler
#: correctly refuses to treat the in-cell run as a delimiter, which leaves three
#: backticks standing in the text, and the evidence reader's single-backtick inline
#: pattern then pairs them with the neighbouring citation's opener. They are here so
#: the batch cannot "fix" the blindness by creating a second, different blindness.
_SIBLING_CITATIONS = (
    "test_late_registration_never_silently_replaces_a_builtin",
    "test_override_is_explicit_and_leaves_an_audit_trail",
)

#: The two exemption rows this batch adds, named once so the disposition leg and the
#: liveness leg cannot drift onto different keys.
_MERGED_RULER_ROWS = (
    "test_witness_script_exists",
    "tests/test_the_require_text_have_one_home.py",
)

#: One text, both failure directions. Written so the right answer is known by
#: construction rather than read off a run: line 3's citation is prose and must be
#: judged, line 6's is inside a real fence and must not.
_PROSE_MENTION_TEXT = (
    "前面 `tests/test_before.py` 要判断。\n"
    "这里提到一个标记：```\n"
    "这一行 `tests/test_swallowed.py` 也要判断。\n"
    "真围栏开在行首：\n"
    "```python\n"
    "示例里写 `test_inside_a_real_block` 不是引用。\n"
    "```\n"
    "结尾 `tests/test_after.py` 也要判断。\n"
)


def _spans(text: str) -> set[str]:
    return {span for _off, span in dp._code_spans(text)}


def _block_of(text: str, offset: int) -> tuple[int, int] | None:
    for start, end in dp._fence_blocks(text)[0]:
        if start <= offset < end:
            return (start, end)
    return None


# --------------------------------------------------------------------------- #
# 1. Both directions, in one text — the pair is the point.
# --------------------------------------------------------------------------- #


def test_a_prose_mention_of_a_fence_marker_hides_no_citation_and_leaks_none() -> None:
    harvested = _spans(_PROSE_MENTION_TEXT)
    assert "tests/test_before.py" in harvested, harvested
    assert "tests/test_after.py" in harvested, harvested
    assert "tests/test_swallowed.py" in harvested, (
        "行中间那个 ``` 把后面的真围栏 opener 配成了自己的闭合位，"
        "于夹在中间的那条引用整个被抹成空格——它一个读者都没有"
    )
    assert "test_inside_a_real_block" not in harvested, (
        f"围栏里的是引文不是声明，却被判断了：{sorted(harvested)}"
    )


def test_the_same_pair_of_citations_survives_on_a_tilde_fence() -> None:
    text = (
        "正文里的 `tests/test_outside.py` 要判断。\n"
        "~~~text\n"
        "示例里写 `test_inside_a_tilde_block` 不是引用。\n"
        "~~~\n"
    )
    ranges, unclosed = dp._fence_blocks(text)
    assert len(ranges) == 1 and unclosed == [], (ranges, unclosed)
    harvested = _spans(text)
    assert "tests/test_outside.py" in harvested, harvested
    assert "test_inside_a_tilde_block" not in harvested, (
        "字节尺只配 ```，波浪线围栏里的示例代码于是被当成作者的引用判断了"
    )


_RUN_LENGTH_TEXT = (
    "双反引号包的 `tests/test_single.py` 与 ``tests/test_double.py`` 都要判断。\n"
    "错配的 `tests/test_mismatch.py`` 不是跨度。\n"
    "三反引号包的 ```tests/test_triple.py``` 也要判断。\n"
)


def test_a_span_is_delimited_by_runs_of_the_same_length_not_by_one_backtick() -> None:
    """Run length is the whole rule: opener of N backticks needs a closer of exactly N.

    ``_CODE_SPAN`` cannot say this — it pairs the first backtick it finds with the next one, so the
    mismatched line below reads as a citation, and a fixed-length pattern reads only one of the three
    shapes. Each of those two wrong shapes is a knife in the battery.
    """
    harvested = _spans(_RUN_LENGTH_TEXT)
    assert "tests/test_single.py" in harvested, harvested
    assert "tests/test_double.py" in harvested, harvested
    assert "tests/test_triple.py" in harvested, harvested
    assert "tests/test_mismatch.py" not in harvested, (
        f"一个单反引号配了两个反引号的收尾，也被当成引用判断了：{sorted(harvested)}"
    )


def test_an_outer_backtick_run_does_not_steal_the_span_it_wraps() -> None:
    """The other half of the same rule, and the reason the opener may not start mid-run.

    A prose `` `` `` run lets a backtick-only pattern open a span on the run's *second* character, take
    the one space that follows, and hand the position back past the wrapped citation's own opener — so
    the citation loses its reader and a blank string gains one. Both halves are pinned here because the
    shipped corpus has this exact shape in a table cell, and the corpus leg below cannot see it: the
    blank span is not an evidence shape, so ``check_evidence`` stays green while the citation is gone.
    """
    text = "行里 `` `file.py:NNN` `` 是一个跨度，`minicc/mcp.py` 是另一个。\n"
    harvested = _spans(text)
    assert "file.py:NNN" in harvested, (
        f"外面那对反引号把里面那条的 opener 吃掉了：{sorted(harvested)}"
    )
    assert "minicc/mcp.py" in harvested, harvested
    assert all(span.strip() for span in harvested), (
        f"读出了空白跨度，说明配对从一串反引号的中间开始：{sorted(harvested)}"
    )
    blank: list[str] = []
    for document in dp.DEFAULT_DOCS:
        if not document.exists():
            continue
        blank += [span for _off, span in dp._code_spans(document.read_text(encoding="utf-8", errors="replace"))
                  if not span.strip()]
    assert blank == [], f"语料里读出 {len(blank)} 个空白跨度，前几个：{blank[:4]!r}"


def test_the_evidence_reader_and_the_pointer_reader_blank_the_same_fenced_bytes() -> None:
    """One ruler, not two copies: whatever the mask hides, the evidence reader must hide too."""
    text = (
        "正文里的 `M8-T521` 与 `tests/test_in_prose.py` 都由引用读者判断。\n"
        "```python\n"
        "示例里写 `M8-T999` 与 `tests/test_in_a_block.py` 都不该被判断。\n"
        "```\n"
    )
    assert "M8-T999" in text, "夹具自己就坏了"
    # The pointer reader harvests out of ``_mask_code``, so the mask's own output is its eyesight.
    blanked = dp._blank_fences(text)
    masked = dp._mask_code(text)
    assert "M8-T999" not in blanked, "公共抹除没有抹掉围栏内容，两把尺在下面那步还会各走各的"
    assert "M8-T999" not in masked, "掩码与证据读者抹的不是同一批字节"
    assert blanked.count("\n") == text.count("\n"), "抹除吃了换行，行号会整体搬家"
    harvested = _spans(text)
    assert "tests/test_in_prose.py" in harvested, harvested
    assert "tests/test_in_a_block.py" not in harvested, harvested
    assert "M8-T999" not in harvested, harvested


# --------------------------------------------------------------------------- #
# 2. The shipped corpus, in the same two directions.
# --------------------------------------------------------------------------- #


def test_no_shipped_citation_lies_inside_a_closed_fence_block() -> None:
    offenders: list[tuple[str, str]] = []
    for document in dp.DEFAULT_DOCS:
        if not document.exists():
            continue
        text = document.read_text(encoding="utf-8", errors="replace")
        for offset, span in dp._code_spans(text):
            if _block_of(text, offset) is not None:
                offenders.append((document.name, span))
    assert offenders == [], f"块内逃逸的跨度 {len(offenders)} 条，前几条：{offenders[:4]}"


#: 块体与块外的收尾指针写在夹具里而不是去船上找：全语料里没有「块内裸指针」这条
#: 形状（上面那条腿断言的就是 0），所以这条腿只能靠夹具活。块体里故意放**裸**指针
#: 而不是反引号跨度——内联那一遍会把跨度自己抹掉，掩码跳过公共抹除也看不出来。
_MASK_FENCE_TEXT = (
    "正文里的 `tests/test_in_prose.py` 要判断。\n"
    "```text\n"
    "示例里有一句裸指针：见 tests/test_in_a_block.py 的用法。\n"
    "```\n"
    "收尾：见 tests/test_after.py 的门。\n"
)


def test_the_pointer_readers_mask_blanks_fences_through_the_same_helper() -> None:
    """The mask is the pointer reader's eyesight, so its fence pass must be the shared one.

    Leg 1's fenced block is made of inline spans, so the mask's *inline* pass erases it even when the
    fence pass is gone — that leg cannot see this clause (measured: the A10 knife left all 12 legs
    green). Only a bare pointer inside the block separates the two passes: with the shared blanker the
    whole region is spaces before the marker walk; without it the example's documentation pointer is
    harvested as if the author had cited it.
    """
    masked = dp._mask_code(_MASK_FENCE_TEXT)
    assert masked.count("\n") == _MASK_FENCE_TEXT.count("\n"), "掩码动了行数，判决会整体搬家"
    body = masked.splitlines()[2]
    assert set(body) <= {" "}, f"围栏体没被抹平，掩码与证据读者抹的不是同一批字节：{body!r}"
    harvest = [span for _off, span, _box, _gap in dp._pointer_spans(_MASK_FENCE_TEXT)]
    assert any(span.startswith("tests/test_after.py") for span in harvest), (
        f"块外的真指针没了——掩码退化成了全抹：{harvest}"
    )
    assert all("tests/test_in_a_block.py" not in span for span in harvest), (
        f"块内的裸指针被当引用收走了，掩码没有走过公共抹除：{harvest}"
    )


def test_the_sibling_citations_keep_their_reader_and_their_line() -> None:
    """The anti-regression leg: green before this batch, and it must stay green after it.

    A block-ruler swap that left the inline pattern alone would turn this leg red — which
    is why the pair is named here instead of folded into leg 1. It is a ceiling leg: it
    proves nothing about the defect, only that the repair does not manufacture a second one.
    """
    text = _ROADMAP.read_text(encoding="utf-8")
    offsets = {span: off for off, span in dp._code_spans(text) if span in _SIBLING_CITATIONS}
    for citation in _SIBLING_CITATIONS:
        assert citation in offsets, f"{citation} 没有读者了：换尺换掉了它的定界符"
        written = next(
            number
            for number, line in enumerate(text.splitlines(), start=1)
            if f"`{citation}`" in line
        )
        reported = dp._line_of(text, offsets[citation])
        assert reported == written, f"{citation} 判在 {reported} 行，作者写的是 {written} 行"


def test_an_unclosed_opener_does_not_swallow_the_rest_of_the_document() -> None:
    """Ceiling leg, and the reason an unclosed opener is *reported* rather than honoured.

    Blank-to-EOF is what a byte reader does when it simply gives up on pairing; the
    line-anchored reader keeps judging the prose below, so the loss shows up as a
    complaint about the document instead of a clean run.
    """
    text = (
        "正文里的 `tests/test_before_the_stray_opener.py` 要判断。\n"
        "这里开了一个再没关掉的围栏：\n"
        "```python\n"
        "而 `tests/test_after_the_stray_opener.py` 也仍然要判断——未闭合不抹到文末\n"
    )
    ranges, unclosed = dp._fence_blocks(text)
    assert ranges == [], ranges
    assert len(unclosed) == 1, unclosed
    harvested = _spans(text)
    assert "tests/test_before_the_stray_opener.py" in harvested, harvested
    assert "tests/test_after_the_stray_opener.py" in harvested, harvested


# --------------------------------------------------------------------------- #
# 3. The repair is not a widened ruler: three dispositions, each named by its carrier.
# --------------------------------------------------------------------------- #


def test_the_dispositions_name_their_own_carriers() -> None:
    """Each of the three citations the merged ruler newly charges has one of two remedies.

    Two are *retired* referents (the document records a rename or a deletion, so the reader needs a row
    that says so). The third is a mis-spelled referent: ROADMAP L20788 lists memo carriers by module stem
    and one stem happens to read like a test function — it means ``minicc/agent/test_selection.py``, and
    admitting source-module stems into the reader would have excused a genuinely missing ``test_selection``
    forever. Population measured before the batch: 1 span out of 776 bare ``test_*`` occurrences.
    """
    assert "test_witness_script_exists" in dp._RETIRED_TEST_NAME, sorted(dp._RETIRED_TEST_NAME)
    assert "tests/test_the_require_text_have_one_home.py" in dp._RETIRED_PATH, sorted(dp._RETIRED_PATH)
    assert "minicc/agent/test_selection.py" in _spans(_ROADMAP.read_text(encoding="utf-8")), (
        "第 3 条处置是把引用改成它的载体；把它改回裸名就等于给读者放宽一档"
    )
    for key, table in (
        ("test_witness_script_exists", dp._RETIRED_TEST_NAME),
        ("tests/test_the_require_text_have_one_home.py", dp._RETIRED_PATH),
    ):
        assert table[key].strip(), f"{key} 的豁免没有理由，等于没豁免"


def test_the_shipped_roadmap_answers_every_evidence_shaped_citation() -> None:
    problems, checked = dp.check_evidence(_ROADMAP, _ROADMAP.read_text(encoding="utf-8"))
    assert checked > 0, "ROADMAP 一个证据形状都没读到，这条腿就什么都没说"
    assert problems == [], [f"{p.kind} {p.line}: {p.detail}" for p in problems]


def test_the_evidence_reader_has_one_fence_ruler_and_no_private_copy() -> None:
    """The defect was a second copy of one rule, so a leg has to charge the copy itself.

    ``_blank_fences`` is the single place that turns fenced bytes into blanks. If either reader grows its
    own pairing again, the ranges stop being the same object and this leg goes red before any citation
    silently changes reader.
    """
    assert hasattr(dp, "_blank_fences"), "证据读者没有走公共的围栏抹除，它又在本地配对"
    assert not hasattr(dp, "_FENCE"), "字节配对的旧尺还留在文件里：两把尺随时会再分叉"
    text = _PROSE_MENTION_TEXT
    blanked = dp._blank_fences(text)
    assert len(blanked) == len(text), "抹除改了字节长度，跨度偏移从此对不上原文"
    for start, end in dp._fence_blocks(text)[0]:
        body = blanked[start:end]
        assert set(body) <= {" ", "\n"}, f"{start}..{end} 没被抹平，两把尺又分开了"
        assert body.count("\n") == text[start:end].count("\n"), "抹除吃掉了换行，行号会整体搬家"
    assert blanked.count("`") < text.count("`"), "公共抹除没有作用：围栏区间里还留着定界符"
    # …and the mask reaches it through the same helper, not a re-implemented loop.
    assert dp._mask_code(text).count("`") <= blanked.count("`"), "掩码与证据读者抹的不是同一批字节"


def test_no_exemption_row_is_dead_after_the_rulers_merge() -> None:
    documents = [p for p in dp.DEFAULT_DOCS if p.exists()]
    problems = dp.check_exempt_tables(documents)
    assert problems == [], [p.detail for p in problems]
    usage = dp.exemption_usage(documents)
    # ``.get`` rather than ``[key]`` on purpose: a row that was deleted outright must show up as the
    # same verdict as a row nobody reaches, and a KeyError would grade as a crash instead of a red.
    dead = [key for key in _MERGED_RULER_ROWS if usage.get(key, 0) == 0]
    assert dead == [], f"合并尺之后这些豁免一条在仓引用都没命中，是死行：{dead}"
