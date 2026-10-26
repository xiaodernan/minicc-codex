"""Gate for the reader that decides which ``` lines are fences at all.

The shipped ``_mask_code`` blanked ``re.sub(r"```.*?```", …, flags=re.S)``: pairing by
**byte order**, anywhere in the document, without asking whether the run *starts* its line.
Two lines in the roadmap do not start a block, they talk about one - L1550 writes
``逐 ```python``` 块 exec`` inside a table cell and L17119 writes ``（` ``` `）`` - and the
second of those is a lone run, so from that line to the end of the file every real block
boundary sits one off. The prose *between* mispaired fences was therefore blanked as code,
and the reader counted nothing, reported nothing, and exited 0.

Measured on ``be7d787`` with the two readings over the 20 shipped documents:

* markers **657 → 825**, checked **104 → 113**, verdicts **0 → 0**;
* comparing per ``(line, span, box)``: **168** pointers handed back to the gate,
  **0** taken away - the fix is monotone, which is what makes the direction claimable;
* the accident that surfaced it: appending one properly-closed fenced block to the roadmap
  made the old reader lose **23** pointers *above* the append, ``--check`` still green.

The rule this batch adopts is the one a renderer uses, stated as three clauses - each of
them charged to an arm below, and two of them (indent, bare-closer) provably invisible on
the corpus, which is why the synthetic fixtures exist:

1. only a run that is its line's first content, indented by at most three spaces, is a
   delimiter;
2. a line carrying a second run of the same character is prose;
3. once a block is open, only a **bare** run (no info string), of the **same character**
   and **at least the opener's length**, closes it.

An opener that never closes is now a verdict (``kind == "FENCE"``, naming its line) instead
of a silent swallowing: the fallback keeps judging the prose below it, so a document that
hides half its page shows up as a complaint.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "doc_pointers.py"


def _load(name: str = "minicc_doc_pointers_t519") -> object:
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # scripts/ is not a package; the dataclasses inside resolve annotations through
    # sys.modules, so the module has to be registered before it executes.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


dp = _load()

#: The predecessor, kept here on purpose. ``C9`` and ``C10`` claim the new reader is
#: *monotone* with respect to it, and a monotonicity claim needs the earlier rule in the
#: room. This is a fossil, not a second implementation of the live grammar: nothing else
#: in this file calls it.
def _old_reader(text: str) -> str:
    blanked = re.sub(r"```.*?```", lambda m: " " * len(m.group(0)), text, flags=re.S)
    return re.sub(r"`[^`\n]*`", lambda m: " " * len(m.group(0)), blanked)


def _spans(text: str) -> list[tuple[int, str, str]]:
    """(line, span, box) for every marker the live reader harvests."""
    return [
        (dp._line_of(text, offset), span, box)
        for offset, span, box, _targets in dp._pointer_spans(text)
    ]


def _spans_under(mask, text: str) -> list[tuple[int, str, str]]:
    """Ask the *pointer* reader to harvest through a given mask, then put the module back."""
    saved = dp._mask_code
    dp._mask_code = mask
    try:
        return _spans(text)
    finally:
        dp._mask_code = saved


def _names(text: str) -> list[str]:
    return [span for _line, span, _box in _spans(text)]


#: A document that mentions fences in prose *and* holds one real block. Inside the block a
#: pointer is a quotation; outside it, a claim. The prose shapes are the two the roadmap
#: actually shipped: a table cell with the run twice, and a run glued into a sentence.
PROSE_MENTIONS = """# 围栏测试

```python``` 同一行里出现两个栅口，这一行在讲围栏而不是开围栏。

README 的安装示例把命令写在 ``` 里，栅口不在行首，同样只是说说。

```text
结论见第 9 节
```

结论见第 2 节。

## 1. 第一节

## 2. 第二节
"""

#: The only text in this file where a pointer *should* resolve: 第 2 节 is declared above it.
_WITH_TARGET = """# 围栏测试

```text
结论见第 9 节
```

结论见第 2 节。

## 1. 第一节

## 2. 第二节
"""


def test_a_prose_mention_of_a_fence_opens_no_block() -> None:
    """The defect, in one document: two prose mentions and one real block.

    Both refusals are the renderer's own: a run that is not its line's first content opens
    nothing, and a backtick fence whose info string holds another backtick is not a fence
    either - which is what a line-initial `` ```python``` `` is. Under byte-order pairing
    the lone run on the second prose line pairs with the block's opener, so the block's
    content stops being code and the gate harvests 见第 9 节 - a quotation it has always
    promised not to invoice.
    """
    ranges, openers = dp._fence_blocks(PROSE_MENTIONS)
    assert len(ranges) == 1, f"两处散文提及被当成了栅口：{ranges}"
    assert openers == []
    start, end = ranges[0]
    assert PROSE_MENTIONS[start:end].startswith("```text"), PROSE_MENTIONS[start:end][:20]
    assert "第 2 节" in _names(PROSE_MENTIONS)
    assert "第 9 节" not in _names(PROSE_MENTIONS), "块内引用又被当成断言收进来了"


def test_an_indented_fence_still_hides_its_content_and_a_fourth_column_run_hides_nothing() -> None:
    """Indent is part of the rule, and it cuts both ways.

    The roadmap ships twelve fences indented by two or three spaces inside numbered lists,
    so an opener that demands column 0 would un-mask their contents. A run at four spaces
    is an indented code block to the renderer, so it must not steal the parity either.
    Neither case has any traffic in the corpus - the reading is identical to the fixed one -
    which is exactly why this leg exists.
    """
    text = (
        "# T\n\n"
        "  ```text\n"
        "  缩进两格：见第 8 节\n"
        "  ```\n\n"
        "    ```text\n"
        "    缩进四格不算栅口：见第 7 节\n"
        "    ```\n\n"
        "块外：见第 6 节。\n"
    )
    names = _names(text)
    assert "第 8 节" not in names, names
    assert "第 7 节" in names and "第 6 节" in names, names
    assert len(dp._fence_blocks(text)[0]) == 1


def test_only_a_bare_run_closes_a_block() -> None:
    """A closing fence may not carry an info string, and the roadmap's own blocks depend on it.

    `` ```text `` inside an open block is content. Let it close and everything after it
    flips into prose-or-code again, one block at a time.
    """
    text = (
        "# T\n\n"
        "```python\n"
        "第一行：见第 5 节\n"
        "```text\n"
        "第二行：见第 6 节\n"
        "```\n\n"
        "块外：见第 4 节。\n"
    )
    names = _names(text)
    assert names == ["第 4 节"], names
    assert len(dp._fence_blocks(text)[0]) == 1, "带信息串的那一行被当成了关栅口"


def test_a_shorter_run_does_not_close_a_longer_block() -> None:
    text = (
        "# T\n\n"
        "````markdown\n"
        "见第 5 节\n"
        "```\n"
        "还是块内：见第 6 节\n"
        "````\n\n"
        "块外：见第 4 节。\n"
    )
    assert _names(text) == ["第 4 节"], _names(text)


def test_a_tilde_block_is_closed_only_by_a_tilde_run() -> None:
    text = (
        "# T\n\n"
        "~~~text\n"
        "见第 5 节\n"
        "```\n"
        "还是块内：见第 6 节\n"
        "~~~\n\n"
        "块外：见第 4 节。\n"
    )
    assert _names(text) == ["第 4 节"], _names(text)
    ranges, openers = dp._fence_blocks(text)
    assert len(ranges) == 1 and openers == []
    assert text[ranges[0][0] : ranges[0][0] + 3] == "~~~"


def test_blanking_keeps_every_offset_and_every_line() -> None:
    """The mask may not move the page.

    Blanking a block to ``" " * len(block)`` keeps the byte offsets - which is what the
    older docstring promised - and destroys the line numbers, so a pointer would be
    reported at a line nobody wrote it on. Both halves are charged here.
    """
    masked = dp._mask_code(PROSE_MENTIONS)
    assert len(masked) == len(PROSE_MENTIONS)
    assert masked.count("\n") == PROSE_MENTIONS.count("\n")
    for start, end in dp._fence_blocks(PROSE_MENTIONS)[0]:
        assert set(masked[start:end]) <= {" ", "\n"}, repr(masked[start:end][:40])
        assert PROSE_MENTIONS[start:end].strip(), "栅口本身是空的？扫描范围不对"
    for offset, _span, _box, _t in dp._pointer_spans(PROSE_MENTIONS):
        assert dp._line_of(masked, offset) == dp._line_of(PROSE_MENTIONS, offset), offset
    for document in dp.DEFAULT_DOCS[:3]:
        text = document.read_text(encoding="utf-8")
        blanked = dp._mask_code(text)
        assert len(blanked) == len(text) and blanked.count("\n") == text.count("\n"), document.name


def test_an_unclosed_opener_is_judged_once_and_named_by_its_line() -> None:
    """Fail-visible: the tail stays read, and the document gets told its fence is open.

    Two halves, and the second one is the point of the choice. A reader that blanked to
    EOF would keep the corpus green while hiding everything below the opener - which is the
    same silence this batch is fixing, one line further down.
    """
    text = (
        "# T\n\n"
        "结论见第 2 节。\n\n"
        "```\n\n"
        "渲染器把这里当代码，本读者不当：还有一句见第 3 节。\n\n"
        "## 1. 第一节\n\n"
        "## 2. 第二节\n"
    )
    problems, checked, _boxes = dp.check_pointers(Path("synthetic.md"), text)
    fences = [problem for problem in problems if problem.kind == "FENCE"]
    assert len(fences) == 1, problems
    assert fences[0].line == 5, fences[0]
    assert "围栏" in fences[0].detail and "闭合" in fences[0].detail, fences[0].detail
    assert "第 3 节" in _names(text), "未闭合的栅口把它之后的正文削掉了"
    assert checked == 2, f"两条指针该都被判到，实测 checked={checked}"
    assert any(problem.kind == "POINTER" and "第 3 节" in problem.detail for problem in problems), problems


def test_the_shipped_corpus_holds_no_unclosed_opener_and_the_account_keeps_its_floor() -> None:
    """The new verdict is not a hair trigger, and the fix has to stay in the numbers.

    The judgment's own traffic is the leg above (an unclosed opener in a fixture); this leg
    is the census: 20 documents, none of them trips it, and at least 150 blocks really
    closed - so a scanner that matched nothing would not pass. The floors are read from the
    same loop that harvests, never typed in from another run.
    """
    blocks = openers = 0
    markers = checked = 0
    for document in dp.DEFAULT_DOCS:
        text = document.read_text(encoding="utf-8")
        ranges, unclosed = dp._fence_blocks(text)
        blocks += len(ranges)
        openers += len(unclosed)
        problems, pointer_count, boxes = dp.check_pointers(document, text)
        markers += sum(boxes.values())
        checked += pointer_count
        assert [p for p in problems if p.kind == "FENCE"] == [], document.name
    assert openers == 0, "语料里出现了未闭合的栅口"
    assert blocks >= 150, f"闭合的围栏只剩 {blocks} 块，扫描器自己看不见了"
    assert markers >= 800, f"全文 markers 掉到 {markers}：这一批的 +168 条又隐形了"
    assert checked >= 100, f"全文 checked 掉到 {checked}：修好的读者又被削回 104 以下"


def test_the_line_anchored_reading_hides_nothing_the_byte_order_one_saw() -> None:
    """Monotonicity, through the predecessor's own return.

    Every ``(line, span, box)`` the old pairing harvested is still harvested, and the new
    reading hands back at least a hundred pointers it could not see. The floor is a floor,
    not today's number: 168 today, and prose only ever moves *further* from a lone run.
    """
    gained = 0
    for document in dp.DEFAULT_DOCS:
        text = document.read_text(encoding="utf-8")
        old = Counter(_spans_under(_old_reader, text))
        new = Counter(_spans(text))
        missing = list(old - new)
        assert not missing, f"{document.name} 比旧读者少看见了 {len(missing)} 条：{missing[:3]}"
        gained += sum((new - old).values())
    assert gained >= 100, f"按行锚定只交回 {gained} 条引用，这一批的落点已经消失"


def test_appending_a_fenced_block_un_counts_nothing_above_it() -> None:
    """The landing accident, made permanent.

    A record is appended to the end of a document, and the old reader loses 23 pointers
    that were already counted *before* the append: the appended opener joins the pairing
    and re-draws every block boundary after the last unpaired run. ``--check`` stayed green
    both times. Appending must be an inert operation for everything above it.
    """
    text = (REPO_ROOT / "docs" / "ROADMAP_TO_PRODUCT.md").read_text(encoding="utf-8")
    appended = text + "\n```text\n这块代码里写着见第 9999 节。\n```\n"
    before = Counter(_spans(text))
    after = Counter(_spans(appended))
    lost = list(before - after)
    assert not lost, f"追加一段围栏抹掉了 {len(lost)} 条已有指针：{lost[:3]}"
    assert "第 9999 节" not in [span for _l, span, _b in after]
    assert dp._fence_blocks(appended)[1] == []


def test_the_mask_still_masks_because_blinding_it_is_not_the_fix() -> None:
    """The other direction: a pointer inside a real block or a real inline span stays a quotation.

    Removing the mask would also make the roadmap's prose visible, so the monotonicity legs
    above stay green while the original promise - ``见「第十八批 M8-T34」`` written as an
    example is not an invoice - is gone.
    """
    inline = "# T\n\n本文用 `见「第十八批 M8-T34」` 举例，另有一句见第 2 节。\n\n## 2. 第二节\n"
    assert "第十八批 M8-T34" not in _names(inline), _names(inline)
    assert _names(_WITH_TARGET) == ["第 2 节"], _names(_WITH_TARGET)
    masked = dp._mask_code(_WITH_TARGET)
    assert masked != _WITH_TARGET, "掩码没有改动任何字节，等于没掩"
    assert "结论见第 9 节" in _WITH_TARGET and "见第 9 节" not in masked.replace("\n", " ")
