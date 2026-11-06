"""M8-T560: a foreign section table is read once and answered without a line ruler.

A pointer that names another document (``见 docs/X.md 第N节``) is resolved by reading that
document's level-2 headings.  Until this batch the resolver called ``sections`` - the
whole-document pipeline that numbers every heading - on every named file, every time a
pointer named it: one pass over the shipped corpus asked a line number for every heading of
documents that were *not* under check, built the same table twice for two pointers into one
document, and read a third document again for an id registry the same pass had already
answered from another reader.

The repair separates the two questions the old pipeline answered at once.  ``_headlines``
finds a heading and the text beneath it and pays no line ruler at all; ``sections`` is that
list plus a line number, for the one document actually under check.  Foreign tables are
built from ``_headlines`` over bytes read through a single memoised door, so each named
document is read once per pass and never numbered.  A document that names itself is answered
from the text the checker was handed, not from the copy on disk - the two can differ, and the
text is the one being judged.

The legs below measure the doors rather than trusting the split: a census over the shipped
source (armed with a planted hand-copy), a byte-for-byte comparison of the lean table with
the old one for every shipped document, the self-citation pair where two identical sentences
get opposite verdicts because they were handed to different documents, a span that declares
no id and must therefore open nothing, a three-citation check whose read count is the whole
point, and the corpus pass itself.

The counts this file measures are reported by the assertions that read them; the batch
record is the place where they are written down.
"""

from __future__ import annotations

import ast
import collections
import importlib.util
import pathlib
import sys
from typing import Any, Iterable

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "doc_pointers.py"


def _load(name: str = "minicc_doc_pointers_t560") -> Any:
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # scripts/ is not a package; @dataclass(slots=True) resolves annotations through
    # sys.modules, so the module has to be registered before it is executed.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


dp = _load()

#: The functions that may decide what a named document says.  Their reads are the bill this
#: file prices; the evidence and name readers open files of their own, for other questions.
DOORS = ("_cross_document_sections", "_numbered_sections", "check_pointers")
READ_CALLERS = frozenset({*DOORS, "_document_text"})

#: Calls that would rebuild the table by hand or read the named file outside the one door.
FORBIDDEN = {
    "_cross_document_sections": frozenset(
        {"read_text", "sections", "_numbered_headings", "_line_of", "_newline_index"}),
    "_numbered_sections": frozenset({"read_text", "sections", "_line_of", "_newline_index"}),
    "check_pointers": frozenset({"read_text"}),
}

#: The call each door must still make, so "no forbidden call" cannot be satisfied by a door
#: that stopped answering at all.
REQUIRED = {
    "_cross_document_sections": frozenset({"_numbered_sections"}),
    "_numbered_sections": frozenset({"_headlines"}),
    "check_pointers": frozenset(),
}


def _callee(call: ast.Call) -> str:
    node = call.func
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def door_offences(source: str, doors: Iterable[str] = DOORS) -> dict[str, list[str]]:
    """Per door, the forbidden calls it makes and the required call it lost."""
    functions = {node.name: node for node in ast.parse(source).body
                 if isinstance(node, ast.FunctionDef)}
    found: dict[str, list[str]] = {}
    for door in doors:
        definition = functions.get(door)
        if definition is None:
            found[door] = ["missing-function"]
            continue
        callees = {_callee(call) for call in ast.walk(definition)
                   if isinstance(call, ast.Call)}
        offences = sorted(f"forbidden:{name}" for name in callees & FORBIDDEN[door])
        offences += sorted(f"missing:{name}" for name in REQUIRED[door] - callees)
        if offences:
            found[door] = offences
    return found


#: The hand-copy this batch retires, planted so the census is judged against a shape it can see.
_HAND_COPY = '''
def _cross_document_sections(text, offset, numeral):
    found = []
    for path in _named_documents(text, offset):
        target = _numbered_headings(sections(path.read_text(encoding="utf-8"))).get(numeral)
        if target is not None:
            found.append(target)
    return found
'''

#: The repaired shape, written the way the shipped door spells it.
_LEAN_DOOR = '''
def _cross_document_sections(document, text, offset, numeral, numbered):
    found = []
    for path in _named_documents(text, offset):
        target = (numbered.get(numeral) if _same_document(path, document)
                  else _numbered_sections(path).get(numeral))
        if target is not None:
            found.append(target)
    return found


def _numbered_sections(path):
    return _numbered_headings(_headlines(_document_text(path)))
'''

#: A door that reads the file itself, planted to show the ``read_text`` rule can fire.
_ID_READ = '''
def check_pointers(document, text):
    registry = set()
    for path in _named_documents(text, 0):
        registry |= _id_registry(path.read_text(encoding="utf-8"))
    return registry
'''


def test_the_numeral_doors_never_read_the_file_or_rebuild_the_table_by_hand() -> None:
    """The shipped doors, read off the source: one door for foreign bytes, no line ruler.

    The hand-copy this batch retired is planted next to the repaired shape: the census
    charges the copy on both counts (it reads the file and it rebuilds the table) and clears
    the door that asks the memoised reader instead.  Without the planted half, a census that
    stopped walking the source would read exactly like a repaired repository.
    """
    shipped = door_offences(SCRIPT.read_text(encoding="utf-8", errors="replace"))
    assert shipped == {}, shipped
    copy = door_offences(_HAND_COPY, ("_cross_document_sections",))
    assert copy == {"_cross_document_sections": [
        "forbidden:_numbered_headings", "forbidden:read_text", "forbidden:sections",
        "missing:_numbered_sections",
    ]}, copy
    assert door_offences(_LEAN_DOOR, ("_cross_document_sections", "_numbered_sections")) == {}
    id_read = door_offences(_ID_READ, ("check_pointers",))
    assert id_read == {"check_pointers": ["forbidden:read_text"]}, id_read


def _clear_rulers() -> None:
    """A fresh pass: the CLI checks a corpus once, so the readings below start cold."""
    for name in ("_numbered_sections", "_document_text"):
        ruler = getattr(dp, name, None)
        if ruler is not None and hasattr(ruler, "cache_clear"):
            ruler.cache_clear()


def test_the_foreign_table_is_the_corpus_table_without_a_line_number() -> None:
    """The lean reader must be the *same rule*, not a second notion of what owns a number.

    For every shipped document the numeral map and each heading's (title, body) have to match
    the table built by ``sections``; what must not match is the type, because the foreign
    answer carries no line number at all.  A different rule here would be the hand-copy
    defect returning in a quieter form - two readers that agree today and drift tomorrow.
    """
    _clear_rulers()
    numerals = 0
    for document in dp.DEFAULT_DOCS:
        text = document.read_text(encoding="utf-8")
        strict = dp._numbered_headings(dp.sections(text))
        lean = dp._numbered_sections(document)
        assert set(lean) == set(strict), (document.name, sorted(lean), sorted(strict))
        assert {n: (h.title, h.body) for n, h in lean.items()} == (
            {n: (h.title, h.body) for n, h in strict.items()}), document.name
        assert all(not hasattr(heading, "line") for heading in lean.values()), (
            document.name, "外来表仍然带着行号：尺子还在这条路上")
        numerals += len(lean)
    assert numerals > 0, "语料里一条编号章节都没有：这条腿是空的"
    plugin = REPO_ROOT / "docs" / "PLUGIN_API.md"
    assert dp._numbered_sections(plugin).get(3) is not None, (
        "前提没了：docs/PLUGIN_API.md 的第3节不在，自指对照就没有可用的编号")


def _numeral_reads(document: pathlib.Path, text: str) -> tuple[list[pathlib.Path], list[Any], int]:
    """Run one check cold and collect the markdown files the numeral doors opened."""
    _clear_rulers()
    reads: list[pathlib.Path] = []
    original = pathlib.Path.read_text

    def spy(self: pathlib.Path, *args: Any, **kwargs: Any) -> str:
        if sys._getframe(1).f_code.co_name in READ_CALLERS:
            reads.append(pathlib.Path(self))
        return original(self, *args, **kwargs)  # type: ignore[arg-type]

    pathlib.Path.read_text = spy  # type: ignore[method-assign]
    try:
        problems, checked, _boxes = dp.check_pointers(document, text)
    finally:
        pathlib.Path.read_text = original  # type: ignore[method-assign]
    return reads, problems, checked


def test_a_document_that_names_itself_is_answered_from_the_text_under_check() -> None:
    """The wrong ruler: a path is not a promise that the disk still holds the text under check.

    Four readings of two sentences.  ``README.md 第8节`` written *in* README's own text is
    answered from that text (green, no file opened).  The same numeral pointing at PLUGIN is
    still red: the self rule must key on the resolved path, not on "we already have a table".
    ``[docs/PLUGIN_API.md](...) 第3节`` is red when the checked document *is* PLUGIN and its
    text declares no 第3节 - the disk copy once made that green - and green when the same
    sentence is handed to a different document.
    """
    readme = dp.REPO_ROOT / "README.md"
    plugin = dp.REPO_ROOT / "docs" / "PLUGIN_API.md"
    elsewhere = pathlib.Path("synthetic.md")
    own_eight = "## 8. 继续实施\n\n正文。\n\n"
    own_one = "## 1. 甲\n\n正文。\n\n"
    linked_three = "复核见 [docs/PLUGIN_API.md](docs/PLUGIN_API.md) 第3节。\n"

    reads, problems, checked = _numeral_reads(readme, own_eight + "结论见 README.md 第8节。\n")
    assert checked == 1, checked
    assert problems == [], problems
    assert reads == [], f"自指还去读了盘上的字节：{[p.name for p in reads]}"

    reads, problems, _checked = _numeral_reads(
        readme, own_eight + "结论见 docs/PLUGIN_API.md 第8节。\n")
    assert [problem.detail for problem in problems] == [
        "「docs/PLUGIN_API.md 第8节」 说第8节在 docs/PLUGIN_API.md 里，那里查不到这个编号的章节"
    ], problems
    assert [path.name for path in reads] == ["PLUGIN_API.md"], [p.name for p in reads]

    reads, problems, _checked = _numeral_reads(plugin, own_one + linked_three)
    assert [problem.detail for problem in problems] == [
        "「[docs/PLUGIN_API.md](docs/PLUGIN_API.md) 第3节」 指向不存在的第3节"
    ], problems
    assert reads == [], f"被检文本没有第3节，却去盘上找到了它：{[p.name for p in reads]}"

    reads, problems, _checked = _numeral_reads(elsewhere, own_one + linked_three)
    assert problems == [], problems
    assert [path.name for path in reads] == ["PLUGIN_API.md"], [p.name for p in reads]


def test_a_span_that_declares_no_id_reads_no_named_document() -> None:
    """The id registry is asked for only when the span declares ids.

    An unresolved batch citation with no numeral still reaches the id fallback, and its
    sentence can name a markdown file.  With no id in the span there is nothing to look up,
    so the named file must not be opened.  On the pre-fix tree the corpus pass reaches this
    block 72 times without an id; the full sequence issues exactly one read through it
    (ROADMAP_TO_PRODUCT.md naming AUDIT_2026-09-20.md).  The sentence below is the smallest
    witness of the clause.
    """
    text = "## 1. 甲\n\n正文。\n\n见 第九百九十九批（对照 docs/AUDIT_2026-09-20.md）。\n"
    reads, problems, checked = _numeral_reads(pathlib.Path("synthetic.md"), text)
    assert checked == 1, checked
    assert reads == [], f"跨度没有申报任何 id，却为 id 登记表读了 {[p.name for p in reads]}"
    assert [problem.detail for problem in problems] == [
        "「第九百九十九批（对照 docs/AUDIT_2026-09-20.md）」 指向不存在的段落「第九百九十九批」"
    ], problems


def test_every_citation_to_one_document_pays_one_read() -> None:
    """Three citations to one document are one read and one table build.

    The second section ask must be served by the memoised table, and the id registry must be
    built from the same bytes the table was built from - not by opening the file again.  The
    heading scan is counted as well: a door that memoises the file but rebuilds the table on
    every citation has still done the work twice.
    """
    text = (
        "## 1. 甲\n\n正文。\n\n"
        "见 [docs/AUDIT_2026-09-20.md](docs/AUDIT_2026-09-20.md) 第12节。"
        "见 [docs/AUDIT_2026-09-20.md](docs/AUDIT_2026-09-20.md) 第12节。"
        "见 [docs/AUDIT_2026-09-20.md](docs/AUDIT_2026-09-20.md) P0-1。\n"
    )
    shipped_headlines = getattr(dp, "_headlines", None)
    checked_text = text
    builds = {"count": 0}
    if shipped_headlines is not None:
        def counted(text: str) -> list[Any]:
            if text is not checked_text:
                builds["count"] += 1
            return shipped_headlines(text)

        dp._headlines = counted
    try:
        reads, problems, checked = _numeral_reads(pathlib.Path("synthetic.md"), text)
    finally:
        if shipped_headlines is not None:
            dp._headlines = shipped_headlines
    assert checked == 3, checked
    assert problems == [], problems
    assert [path.name for path in reads] == ["AUDIT_2026-09-20.md"], (
        f"同一份外来文档被打开了 {len(reads)} 次：{[p.name for p in reads]}")
    assert builds["count"] == 1, (
        f"同一张外来表建了 {builds['count']} 次：两次章节引用没有共用一次扫描")


def test_the_corpus_pass_reads_each_named_document_once() -> None:
    """The production pass: no named document is opened twice, and only markdown is opened.

    This is the pass the pre-fix defect was measured on.  The population is the shipped
    corpus, and the non-vacuity clause requires at least one named document to be read -
    a pass that resolved no foreign citation would make the duplicate claim empty.
    """
    documents = [(path, path.read_text(encoding="utf-8", errors="replace"))
                 for path in dp.DEFAULT_DOCS]
    _clear_rulers()
    reads: list[pathlib.Path] = []
    original = pathlib.Path.read_text

    def spy(self: pathlib.Path, *args: Any, **kwargs: Any) -> str:
        if sys._getframe(1).f_code.co_name in READ_CALLERS:
            reads.append(pathlib.Path(self))
        return original(self, *args, **kwargs)  # type: ignore[arg-type]

    pathlib.Path.read_text = spy  # type: ignore[method-assign]
    try:
        for document, text in documents:
            dp.check_pointers(document, text)
    finally:
        pathlib.Path.read_text = original  # type: ignore[method-assign]

    counts = collections.Counter(reads)
    duplicates = {path.relative_to(REPO_ROOT).as_posix(): count
                  for path, count in counts.items() if count > 1}
    assert duplicates == {}, (
        f"一次通行里同一份外来文档被开了不止一次：{duplicates}")
    assert 0 < len(counts) < len(documents), (
        f"语料通行没有走到外来文档，或把每一份都读了：{len(counts)} / {len(documents)}")
    assert all(path.suffix == ".md" for path in counts), sorted(counts)
