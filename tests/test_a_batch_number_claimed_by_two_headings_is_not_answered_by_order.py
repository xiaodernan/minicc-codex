"""Gate for the reader that resolves 「第N批」 when two headings claim the same number.

The defect is arbitration, not arithmetic. ``_batch_labels`` built its roster with
``setdefault``, so a batch number declared by two headings landed every pointer on
whichever heading came first in the document. Nothing was reported, and the pointer that
meant the second record silently read the first one. Measured on the shipped roadmap
before this batch: **15** labels were double-claimed (one of them three times), **4** live
checked pointers named one of them — all four 「第二十三批」 — and **2** of those four
provably meant the *other* record, because they cite 「A 段」/「C 段」 and only the second
record has lettered parts. The two readings were byte-identical from the outside: a green
run and a wrong page.

``_batch_claims`` now keeps every claimant, and the check site resolves a double booking
only when the pointer's own ids declare which one it meant. Everything else fails closed.

Why the fall-closed half is load-bearing: after the three corpus repairs in this batch, no
live pointer in the corpus names a double-claimed label any more, so a clause that only
reports ambiguity has **no traffic** outside these fixtures. That is why C1 exists beside
C9, and why every branch below is charged to an arm in the batch's mutation table.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "doc_pointers.py"


def _load(name: str = "minicc_doc_pointers_t517") -> object:
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # scripts/ is not a package; the dataclasses inside resolve annotations through
    # sys.modules, so the module must be registered before it executes.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


dp = _load()

#: The labels the shipped ledger double-books, keyed by label with the number of headings
#: that declare it. Written down on purpose: a *new* double booking has to red here and
#: force somebody to decide which record owns the number, instead of quietly becoming a
#: pointer that answers from document order. Repaired entries leave this map.
DOUBLE_CLAIMED = {
    "第二百批": 2,
    "第二百二十四批": 2,
    "第二百二十五批": 3,
    "第二百六十四批": 2,
    "第二百九十批": 2,
    "第三百六十三批": 2,
    "第三百六十四批": 2,
    "第一百一十一批": 2,
    "第一百三十九批": 2,
    "第一百三十批": 2,
    "第一百四十批": 2,
    "第六十一批": 2,
    "第四百四十五批": 2,
    "第八批续": 2,
}

#: 「第…批」 written the way a record writes its own heading.
_CLAIM = "## 第三十批 {who}{decl}\n\n{who}的正文。"
_POINTER = "结论见「第三十批{said}」。\n"


def _reported(text: str) -> tuple[list[str], int]:
    problems, checked, boxes = dp.check_pointers(Path("synthetic.md"), text)
    assert checked or sum(boxes.values()), "标记一个都没 harvest 到，这条门就是空的"
    return [p.detail for p in problems], checked


def _ledger(
    *,
    first: str = "",
    second: str = "",
    said: str = "",
    swapped: bool = False,
) -> str:
    """A document whose two sections both declare 第三十批, each block three lines long.

    Equal line counts are the point: ``swapped`` exchanges the two blocks and the pointer's
    own line must not move, so the only thing that can change between the two readings is
    which address the verdict pairs with which record.
    """
    甲 = _CLAIM.format(who="甲", decl=first)
    乙 = _CLAIM.format(who="乙", decl=second)
    blocks = [乙, 甲] if swapped else [甲, 乙]
    return "# T\n\n" + "\n\n".join(blocks) + "\n\n" + _POINTER.format(said=said)


def _roadmap() -> Path:
    return next(path for path in dp.DEFAULT_DOCS if path.name == "ROADMAP_TO_PRODUCT.md")


def test_two_claimants_without_evidence_are_named_with_their_addresses() -> None:
    """C1 主判据：一条无证据的指针不许被文档顺序回答，也不许被静默落到某一页上。"""
    problems, checked = _reported(_ledger())
    assert checked == 1, checked
    assert len(problems) == 1, problems
    detail = problems[0]
    assert "2 个申报者" in detail, detail
    # 行号是这条判词的全部用处：读的人要能直接跳到两个候选，而不是再自己搜一遍标题。
    assert "第3行" in detail and "第7行" in detail, detail
    assert "第三十批" in detail, detail


def test_an_id_declared_by_one_claimant_decides_the_landing() -> None:
    """C2 证据支：span 里的 id 只被其中一个申报者声明时，落点由证据定，不是由顺序定。

    两条腿都要：声明者排在**前面**时，旧读者靠顺序也恰好答对，所以那一条在父提交上是绿的
    （它只证明新规则没有把本来对的答案改错）；声明者排在**后面**时，顺序必错，那一条才是
    本批缺陷的形状——旧读者把读者领到第一页，然后说那一页里没有这个编号。
    """
    problems, checked = _reported(_ledger(first=" M8-T9", said=" M8-T9"))
    assert problems == [] and checked == 1, problems
    problems, checked = _reported(_ledger(second=" M8-T9", said=" M8-T9"))
    assert problems == [] and checked == 1, problems


_ADDRESS = re.compile(r"第(\d+)行「(第三十批 [^」]*)」")


def test_exchanging_the_two_claimants_moves_only_their_addresses() -> None:
    """C3 顺序无干：把两个申报者前后对调，判词只换它们各自的地址，骨头文字一字不改。

    两个块等长，所以指针自己那一行不动，能变的只有「哪条记录在第几行」。地址要是还钉在
    第一个块上（或两个申报者共用一个行号），判词就会把读者领到另一条记录那里去。
    """
    forward, _ = _reported(_ledger())
    exchanged, checked = _reported(_ledger(swapped=True))
    assert len(forward) == 1 and len(exchanged) == 1, (forward, exchanged)
    assert checked == 1, checked

    def addresses(detail: str) -> dict[str, int]:
        found = {title: int(line) for line, title in _ADDRESS.findall(detail)}
        assert len(found) == 2, f"判词没有点名两个申报者各自的行号：{detail}"
        return found

    assert addresses(forward[0]) == {"第三十批 甲": 3, "第三十批 乙": 7}, forward[0]
    assert addresses(exchanged[0]) == {"第三十批 乙": 3, "第三十批 甲": 7}, exchanged[0]
    skeleton = r"第<行>行「<申报者>」"
    assert _ADDRESS.sub(skeleton, forward[0]) == _ADDRESS.sub(skeleton, exchanged[0]), (
        forward[0],
        exchanged[0],
    )


def test_evidence_that_fits_both_claimants_decides_nothing() -> None:
    """C4 证据用尽：两个申报者都声明那个 id 时，仍然只能失败闭合。"""
    problems, checked = _reported(_ledger(first=" M8-T9", second=" M8-T9", said=" M8-T9"))
    assert checked == 1, checked
    assert len(problems) == 1 and "2 个申报者" in problems[0], problems


def test_every_id_in_the_span_has_to_fit_the_same_claimant() -> None:
    """C5 `all` 而非 `any`：甲声明两个 id、乙只声明其中一个，乙不算证据。

    按 any 判的话，两条 id 会各自在不同候选那里找到着落，读者以为落点定了，其实只
    有一句里的两个片段各自对上了两页不同的记录。
    """
    problems, checked = _reported(_ledger(first=" M8-T9 M8-T10", second=" M8-T9", said=" M8-T9 M8-T10"))
    assert problems == [] and checked == 1, problems


def test_a_claimant_that_only_mentions_the_id_in_prose_is_not_evidence() -> None:
    """C6 证据走声明，不走提到：把 M8-T9 写在正文里的候选不能赢。

    ``_id_registry`` 读标题与表格名栏；``## 4 …`` 级别的散文提到一个编号不算它属于那一节
    ——和 M8-T37 给 id 定下的口径同一条，指针自己引用的字符串不能自证。
    """
    text = _ledger(second=" M8-T9", said=" M8-T9")
    # 把 id 塞进第一个申报者的正文（散文），声明仍然只在第二个的标题里。
    text = text.replace("甲的正文。", "甲顺手关掉 M8-T9 的缺口。", 1)
    assert "甲顺手关掉 M8-T9" in text and "第三十批 甲 M8-T9" not in text, text
    problems, checked = _reported(text)
    assert problems == [] and checked == 1, problems


def test_a_label_with_one_claimant_is_untouched_and_one_with_none_still_reds() -> None:
    """C7 惰性对照 + 红路径仍在：单候选照常落地，无人申报仍然说「不存在」。"""
    single = "# T\n\n## 第三十一批 甲\n\n结论见「第三十一批」。\n"
    problems, checked = _reported(single)
    assert problems == [] and checked == 1, problems
    missing = "# T\n\n## 第三十一批 甲\n\n结论见「第三十二批」。\n"
    problems, checked = _reported(missing)
    assert checked == 1 and len(problems) == 1, problems
    assert "不存在" in problems[0] and "第三十二批" in problems[0], problems


def test_the_double_booked_labels_in_the_shipped_ledger_are_a_named_roster() -> None:
    """C8 语料普查：名册按申报者数逐格钉住，多一条少一条都要有人来改这张表。"""
    claims = dp._batch_claims(dp.sections(_roadmap().read_text(encoding="utf-8")))
    counts = {label: len(claimants) for label, claimants in claims.items() if len(claimants) > 1}
    assert counts == DOUBLE_CLAIMED, {
        "new": {k: v for k, v in counts.items() if k not in DOUBLE_CLAIMED},
        "gone": {k: v for k, v in DOUBLE_CLAIMED.items() if k not in counts},
    }
    # 本批修掉的那一条：改名之后两个标题各有一个批号，谁也不再抢谁。
    assert [s.line for s in claims["第二十三批"]] == [1826], claims["第二十三批"]
    assert [s.line for s in claims["第二十三批续"]] == [2278], claims["第二十三批续"]


def test_no_pointer_in_the_corpus_lands_on_a_double_booking() -> None:
    """C9 语料天花板：修完语料之后，全文 20 篇一条判词都不该有。

    这条在父提交上是**空绿**——旧读者根本不报歧义，所以它不能证明任何事；它的触达见证
    是 C1。把它留在这里是为了钉住「语料干净」这件事，而不是钉住新 clause。
    """
    dirty = [
        (path.name, problem.line, problem.detail[:80])
        for path in dp.DEFAULT_DOCS
        for problem in dp.check_pointers(path, path.read_text(encoding="utf-8"))[0]
    ]
    assert dirty == [], dirty[:6]


def test_the_batch_roster_has_exactly_one_key_builder() -> None:
    """C10 键的构造只有一家：名册的键集合必须由 ``_batch_label`` 现推，别手抄。

    语料里真有一条带空格的标题（``## 第 203 批 M8-T176``）。谁再在 ``_batch_claims`` 里
    用 ``match.group(0)`` 抄一份键，那条标题就会以两种拼法进名册，指向它的指针从此落不
    上——一个关于存在的段的假红。
    """
    text = _roadmap().read_text(encoding="utf-8")
    headings = dp.sections(text)
    derived = {label for section in headings for label in dp._declared_batch_labels(section.title)}
    assert set(dp._batch_claims(headings)) == derived, sorted(
        set(dp._batch_claims(headings)) ^ derived
    )[:8]
    assert "第 203 批" not in derived and "第203批" in derived, sorted(derived)[:8]


def test_an_ambiguous_landing_does_not_stack_a_second_verdict_on_the_ids() -> None:
    """C11 一条歧义只说一次：落点没定成时，不再按「本文档」审计 span 里的 id。

    叠上去的那句会把读者的定位符也判错——读者以为自己 id 写错了，其实要改的是标题。
    """
    text = _ledger(said=" M8-T404")
    # 让这条 id 在整篇文档里都不存在，否则 doc-wide 兜底会把它自己判绿，这条门就是空的。
    problems, checked = _reported(text)
    assert checked == 1, checked
    assert len(problems) == 1, problems
    assert "申报者" in problems[0], problems[0]
