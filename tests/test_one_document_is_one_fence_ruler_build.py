"""Gates for M8-T540: a corpus leg builds one document's fence ruler a fixed number of times.

``test_no_shipped_citation_lies_inside_a_closed_fence_block`` asks, for every code
span, which closed fence block contains it.  Through the M8-T536 run the question
was asked by re-pairing the **whole document** on every span, so the cost of the leg
was "spans x document": the M8-T532 record measured 24,071 spans x 0.020s ≈ 482s on
a quiet machine; the M8-T536 run took 1423.6s and ``conftest.py:87``'s hook rewrote
its pass into ``failed`` at the 900s bound.  The predicate never went red — the
report said "caught something" about a thing that had finished and found nothing.

This gate holds a **call count**, not a clock: the clock moves with the machine, the
count is a property of the source.  The fixtures are synthetic so both readings are
affordable on both sides of the repair.

Each leg answers a different way the repair could lie:

  * the count — a leg that pays per span again must be red in milliseconds, not at
    the 900s bound; and the count must not move when only the span count moves;
  * the two-document fixture — hoisting the ruler *too far* (one document's ranges
    judging another document's spans) is the new failure a hoist can create;
  * the unit leg — "nothing is ever inside a block" is the old blindness wearing the
    repair's clothes.  No corpus leg can see it: ``_code_spans`` blanks fences before
    it harvests, so ``offenders == []`` is also what a blind predicate prints.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LEG = REPO_ROOT / "tests" / "test_the_two_readers_share_one_fence_ruler.py"


def _load_leg():
    spec = importlib.util.spec_from_file_location("minicc_fence_ruler_leg_t540", LEG)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


leg = _load_leg()

_FENCED = "```python\n示例代码，不含引用。\n```\n"
_PROSE_ONE = "正文里的 `tests/test_one.py` 要判断。\n"
_PROSE_TWO = "正文里的 `tests/test_two.py` 与 `tests/test_three.py` 都要判断。\n"
_MORE = "再多几行：`tests/test_four.py`、`tests/test_five.py`、`tests/test_six.py`。\n"


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8", newline="")
    return path


def test_the_corpus_leg_builds_the_ruler_per_document_not_per_span(tmp_path, monkeypatch) -> None:
    base_a = _write(tmp_path / "base_a.md", _FENCED + _PROSE_ONE)
    base_b = _write(tmp_path / "base_b.md", _PROSE_TWO)
    more_a = _write(tmp_path / "more_a.md", _FENCED + _PROSE_ONE + _MORE)
    more_b = _write(tmp_path / "more_b.md", _PROSE_TWO + _MORE)

    def spans_of(*documents: Path) -> int:
        return sum(len(leg.dp._code_spans(p.read_text(encoding="utf-8"))) for p in documents)

    spans_base = spans_of(base_a, base_b)
    spans_more = spans_of(more_a, more_b)
    assert spans_more > spans_base, "夹具失效：两轮的跨度数一样，这条腿就量不出成本跟谁走"

    real = leg.dp._fence_blocks
    calls: list[str] = []

    def counting(text: str):
        calls.append(text)
        return real(text)

    monkeypatch.setattr(leg.dp, "_fence_blocks", counting)
    run_leg = leg.test_no_shipped_citation_lies_inside_a_closed_fence_block

    monkeypatch.setattr(leg.dp, "DEFAULT_DOCS", [base_a, base_b])
    calls.clear()
    run_leg()
    first_run = list(calls)

    monkeypatch.setattr(leg.dp, "DEFAULT_DOCS", [more_a, more_b])
    calls.clear()
    run_leg()

    assert set(first_run) == {base_a.read_text(encoding="utf-8"), base_b.read_text(encoding="utf-8")}, (
        "这把尺在别的字节上建了：它读的不是这两份文档的原文"
    )
    assert len(first_run) == len(calls), (
        f"同一批文档只多了 {spans_more - spans_base} 个跨度，尺却从 {len(first_run)} 次建到"
        f" {len(calls)} 次——成本跟着跨度走，就是 24,071 次全档重解析那条形状"
    )
    assert len(first_run) >= 2, f"两份文档一尺都没建（{len(first_run)} 次），这条腿没在看"
    assert len(first_run) <= 4, (
        f"{len(first_run)} 次建尺对两份文档：每份最多两次（_code_spans 的空档抹除一次、"
        "这条腿自己一次），再多就是又按跨度数建了"
    )


def test_a_block_in_one_document_does_not_judge_a_citation_in_another(tmp_path) -> None:
    first = _write(tmp_path / "first.md", "```python\n" + "示例代码，不含引用。\n" * 20 + "```\n")
    second = _write(tmp_path / "second.md", "    `tests/test_second.py` 要判断。\n")

    text_first = first.read_text(encoding="utf-8")
    (block_start, block_end), = leg._fence_ranges(text_first)
    offset = next(
        off
        for off, span in leg.dp._code_spans(second.read_text(encoding="utf-8"))
        if span == "tests/test_second.py"
    )
    assert block_start <= offset < block_end, (
        f"夹具失效：第二份文档引用的偏移 {offset} 没落在第一份的块 "
        f"[{block_start}, {block_end}) 里，这条腿就分不清「用了自己的尺」和「用了别人的尺」"
    )
    assert leg._offenders_in_blocks([first, second]) == [], (
        "第二份文档的正文引用被第一份文档的围栏判成了块内——那把尺被举到了文档循环外面"
    )


def test_the_containment_answer_is_known_by_construction() -> None:
    ranges = [(10, 20)]
    assert leg._block_of(ranges, 10) == (10, 20), "块的第一个字节在里面"
    assert leg._block_of(ranges, 19) == (10, 20), "块的最后一个字节在里面"
    assert leg._block_of(ranges, 20) is None, "收尾 run 之后已经是正文"
    assert leg._block_of(ranges, 9) is None
    assert leg._block_of([], 10) is None
