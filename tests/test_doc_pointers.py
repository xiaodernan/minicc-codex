"""Gates for the checker that resolves cross-references in the project's markdown.

The defect this guards is one this repository shipped and then re-shipped:
M8-T34's roadmap row pointed at 「第十八批 M8-T34」, a subsection that does not
exist — the 第十八批 section records M8's exit criteria and never mentions
M8-T34. M8-T35 rewrote that row to explain the mistake, and the new sentence
ended with the *same* broken pointer. Two humans-in-a-row (the same author twice)
reading their own text did not see it; only a second reader that resolves every
pointer mechanically will.

Precision is the hard part, not coverage: ``见`` is a Chinese suffix in 可见,
意见, 预见, 见证, 见收益, so harvesting on the marker alone produced 48 "distinct
pointers" of which almost none were pointers. The rule these tests hold is that
a span counts only when it names a locator (``第N批`` / ``第N节`` / ``附录 X``)
or an id (``M8-T34``, ``M4-3``, ``P0-1``), and a locator plus an id is a claim
about *where* the id lives — the exact claim that was wrong.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "doc_pointers.py"


def _load():
    spec = importlib.util.spec_from_file_location("minicc_doc_pointers", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # scripts/ is not a package; @dataclass(slots=True) resolves annotations via
    # sys.modules, so register the module before executing it.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


dp = _load()

#: A document that contains one correct pointer of every supported shape, plus
#: prose that must *not* be read as a pointer.
_GOOD_DOC = """\
# 测试文档

## 一、第一节

可见、意见、预见、见证、见收益，还有「口径见下方注记」——这些都不是指针。

## 三、第三节

### M4 记录（第二批，2026-09-22）

| M4-3 `POST /api/*` 覆盖 | ✅ | 细节 |

详见「第三节」，也见「第二批 M4-3 行」，附录 A 里另有清单。

## 附录 A：清单
"""

#: The shipped defect, in miniature: a section that exists, an id that exists,
#: and a pointer claiming the id lives in the section when it does not.
_BAD_DOC = """\
# 测试文档

## 四、明确不做什么

| M8-T34 探针 | ✅ | 结论 |

### M8 退出标准真跑记录（第十八批，2026-09-23）

三条全绿。见下方「第十八批 M8-T34」。
"""


def _pointer_problems(text: str) -> list[str]:
    problems, checked, unresolved = dp.check_pointers(Path("synthetic.md"), text)
    assert checked or unresolved
    return [f"{p.detail}" for p in problems]


def test_prose_that_merely_ends_with_the_marker_is_not_harvested() -> None:
    problems, checked, unresolved = dp.check_pointers(Path("synthetic.md"), _GOOD_DOC)
    assert problems == []
    # 「见下方注记」 and friends are counted as a *gap*, not silently dropped.
    assert unresolved >= 2
    assert checked >= 2, "the doc must actually exercise the locator paths"


def test_locator_plus_id_is_a_claim_about_where_the_id_lives() -> None:
    # Positive control: same ids, but the id really is inside the named section.
    assert _pointer_problems(_GOOD_DOC) == []
    problems = _pointer_problems(_BAD_DOC)
    assert len(problems) == 1, problems
    assert "M8-T34" in problems[0]
    assert "第十八批" in problems[0]


def test_pointer_to_a_batch_that_never_existed_is_reported() -> None:
    text = "# T\n\n### 记录（第七批）\n\n内容。见「第九十九批」。\n"
    problems = _pointer_problems(text)
    assert len(problems) == 1
    assert "第九十九批" in problems[0]


def test_a_suffix_that_keeps_growing_still_resolves() -> None:
    text = "# T\n\n### 记录（第十五批续二）\n\nM8-T31 结论。见「第十五批续二」的 M8-T31。\n"
    assert _pointer_problems(text) == []
    # 续 must not be satisfied by the longer 续二 section it prefixes.
    text_missing = "# T\n\n### 记录（第十五批续二）\n\n内容。见「第十五批续」。\n"
    assert len(_pointer_problems(text_missing)) == 1


def test_numbered_section_pointers_use_the_heading_numeral_not_the_words() -> None:
    text = "# T\n\n## 四、明确不做什么\n\n内容。见第四节。\n"
    assert _pointer_problems(text) == []
    assert len(_pointer_problems("# T\n\n## 四、内容\n\n见第十一节。\n")) == 1


def test_appendix_pointers_resolve_by_letter() -> None:
    assert _pointer_problems("# T\n\n## 附录 B：注记\n\n见附录 B。\n") == []
    assert len(_pointer_problems("# T\n\n## 附录 B：注记\n\n见附录 E。\n")) == 1


def test_a_bare_id_pointer_only_has_to_exist_somewhere_in_the_doc() -> None:
    assert _pointer_problems("# T\n\n## 一、x\n\n见 M8-T16 行。\n| M8-T16 429 | ✅ | 结论 |\n") == []
    assert len(_pointer_problems("# T\n\n## 一、x\n\n见 M8-T999 行。\n")) == 1


def test_relative_links_must_resolve_and_urls_are_left_alone(tmp_path: Path) -> None:
    (tmp_path / "real.md").write_text("# real\n", encoding="utf-8")
    text = (
        "[ok](real.md)\n[missing](nope.md)\n[ext](https://example.test/x)\n[frag](#anchor)\n"
    )
    problems, checked = dp.check_links(tmp_path / "doc.md", text)
    assert checked == 2, "the URL and the in-page fragment are not this tool's business"
    assert len(problems) == 1 and "nope.md" in problems[0].detail


def test_cross_document_section_pointer_needs_the_file_named(tmp_path: Path) -> None:
    # 第十二节 does exist in docs/AUDIT_2026-09-20.md; naming the file is what
    # makes such a pointer checkable at all, and the gate holds that line.
    named = "复核命令见 [docs/AUDIT_2026-09-20.md](docs/AUDIT_2026-09-20.md) 第十二节。\n"
    assert _pointer_problems(named) == []
    vague = "复核命令见审核文档第十二节。\n"
    assert len(_pointer_problems(vague)) == 1


def test_floors_fire_when_the_extractor_goes_blind(monkeypatch) -> None:
    document = REPO_ROOT / "docs" / "ROADMAP_TO_PRODUCT.md"
    _, stats = dp.check_document(document)
    assert stats.pointers >= 15
    monkeypatch.setitem(dp.MIN_POINTERS, "docs/ROADMAP_TO_PRODUCT.md", stats.pointers + 1)
    problems, _ = dp.check_document(document)
    assert [p.kind for p in problems] == ["INVENTORY"]
    assert str(stats.pointers) in problems[0].detail


def test_shipped_documents_have_no_dangling_references() -> None:
    problems: list[dp.Problem] = []
    totals = {"pointers": 0, "links": 0}
    for document in dp.DEFAULT_DOCS:
        found, stats = dp.check_document(document)
        problems.extend(found)
        totals["pointers"] += stats.pointers
        totals["links"] += stats.links
    assert problems == []
    # Anti-vacuity: a clean run over an empty inventory would prove nothing.
    assert totals["pointers"] >= 25
    assert totals["links"] >= 15


def test_documented_command_runs_end_to_end() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--quiet"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "DANGLING" not in result.stdout
    assert "pointers" in result.stdout


def test_a_pointer_written_inside_a_code_span_is_a_quotation_not_a_claim() -> None:
    """README illustrates the defect by quoting it; quoting must not be checked.

    Without the masking step this gate is red for the wrong reason — and the
    first version of the tool was, which is how the rule got written down. The
    cost of the rule is honest and recorded: a genuinely dangling pointer that
    someone wrote inside a code span is invisible here, exactly like a prefix
    dispatch is invisible to a ``path ==`` scan.
    """
    quoted = "# T\n\n缺陷长这样：`见「第十八批 M8-T34」`。\n"
    problems, checked, unresolved = dp.check_pointers(Path("synthetic.md"), quoted)
    assert problems == [] and checked == 0
    # Masking blanks the whole span, marker included, so the quotation is never
    # harvested at all — it is not an unresolved marker, it is absent. My first
    # version of this gate asserted ``unresolved == 1`` and was wrong: the tool
    # was already right, and an expectation written from what I wanted the tool
    # to do is the same mistake as a self-satisfying id check.
    assert unresolved == 0

    prose = "# T\n\n结论见「第十八批 M8-T34」。\n"
    prose_problems = dp.check_pointers(Path("synthetic.md"), prose)[0]
    # The unquoted same text is a claim, and a claim in a document with no such
    # section is two complaints: the batch paragraph does not exist, and the id
    # is not declared anywhere. Quoting it is what makes both disappear.
    assert len(prose_problems) == 2, prose_problems
    # Distinguish the two claims by what each one asserts, not by the span text:
    # every detail quotes the whole 「…」, so counting 「第十八批」 there says
    # nothing about which complaint fired.
    assert sum("指向不存在的段落" in p.detail for p in prose_problems) == 1
    assert sum("没有这个编号" in p.detail for p in prose_problems) == 1
