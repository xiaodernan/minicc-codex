"""M8-T556: a line number is asked only for an item the reader has already admitted.

``_line_of`` answers "which line is this offset on?" by counting newlines from the start of the
document up to that offset.  The answer is therefore a *prefix* scan: its price is a function of
how far into the document the item sits, and the reader asks it once per item.  Batch 537 measured
that price, named it as a separate charge, deliberately kept it out of its own roster -- a prefix
is not a whole document -- and registered the family as M8-T556.

What this file measures is not the price but the *waste*: ``check_evidence`` asked for the line
number first and only then tested whether the code span was an evidence claim at all, and
``_check_name_targets`` asked once per citation even when every target inside it was about to be
thrown away by the kind filter.  Both shapes pay a prefix scan for an item nobody judges.  The
legs below run the shipped readers over the corpus the gate really walks (``DEFAULT_DOCS``, plus
pinned documents for the members that corpus never reaches) and compare, per asking function, the
number of line numbers asked against the number of items that same function admitted -- the
admitted count always read from the shipped reader's own channel (the counters it returns, the
per-box counts it returns, the arguments its own caller passes), never from a number typed here.

Two boundaries stay on the record rather than being quietly moved.  ``_line_of`` is still
prefix-bounded, so the roster batch 537 derived still does not contain it -- a later batch that
swaps in a cursor or a per-document index has to re-classify *that* claim, and this file is where
the old shape is pinned.  And the two readings that would replace the prefix count are replayed
here against every captured request: they agree today, which is what makes changing the reading a
free choice later rather than an unmeasured one.
"""

from __future__ import annotations

import ast
import bisect
import collections
import importlib.util
import pathlib
import sys
from typing import Any, Callable

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "doc_pointers.py"
FAMILY = "_line_of"
M555_FILE = "test_a_per_span_answer_re_scans_no_whole_document_ruler.py"
THIS_FILE = pathlib.Path(__file__).name

#: An unclosed fence, a dead link and a page of mixed spans are cold or thin in ``docs/``.  A
#: member judged only by "asked == admitted == 0" is vacuous, so it is handed a document that
#: reaches it instead of being left out of the roster.
PINNED: list[tuple[str, str]] = [
    ("t556_pinned_fence.md", "# T\n\n```python\nprint(1)\n\ntail inside the swallowed block\n"),
    ("t556_pinned_link.md", "# T\n\n[a](t556_missing_target.md)\n\nplain prose follows\n"),
    ("t556_pinned_evidence.md",
     "# T\n\n`scripts/doc_pointers.py:256` 是证据。\n"
     "`tests/test_doc_pointers.py::test_the_checker_reads_a_document` 是证据。\n"
     "`_line_of` 只是一个名字，不是证据。\n"),
]


def _load(name: str = "minicc_doc_pointers_t556") -> Any:
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # scripts/ is not a package; @dataclass(slots=True) resolves annotations through
    # sys.modules, so the module has to be registered before it is executed.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


dp = _load()

#: Every asking function this file knows how to judge, by the channel that admits its items.
CHANNELS = frozenset({"check_evidence", "check_pointers", "_check_quoted_name",
                      "_check_name_targets", "check_links", "sections"})


def _in_scope(document: pathlib.Path) -> bool:
    """The reader's own out-of-scope test, spelled the way the reader spells it."""
    relative = (document.relative_to(REPO_ROOT).as_posix()
                if document.is_relative_to(REPO_ROOT) else document.name)
    return relative not in dp._OUT_OF_SCOPE_DOCS


def _corpus() -> list[tuple[pathlib.Path, str]]:
    """The shipped default population, plus the pinned documents.

    The pinned paths hang off ``docs/`` without being written there: the link reader resolves a
    target against ``document.parent``, so the parent has to be the real one for that member to
    be reached the way the gate reaches it.
    """
    real = [(path, path.read_text(encoding="utf-8", errors="replace")) for path in dp.DEFAULT_DOCS]
    pinned = [(REPO_ROOT / "docs" / name, text) for name, text in PINNED]
    return real + pinned


def _capture() -> dict[str, Any]:
    """One pass of the shipped readers, watching who asks for a line number and what they admit.

    Each request carries whether the text it was asked of *is* the document being checked:
    ``sections`` is also called on another document's bytes (a cross-document citation reads the
    target file), and answering those offsets from the checked document's index would judge a
    different text than the reader handed to the helper.
    """
    if _CAPTURE:
        return _CAPTURE
    asked: dict[str, list[tuple[str, int, int, bool]]] = collections.defaultdict(list)
    current = {"doc": "?", "text": ""}
    shipped = dp._line_of

    def watched(text: str, offset: int) -> int:
        line = shipped(text, offset)
        asked[sys._getframe(1).f_code.co_name].append(
            (current["doc"], offset, line, text is current["text"]))
        return line

    name_calls: collections.Counter[str] = collections.Counter()
    shipped_targets = dp._check_name_targets

    def counted_targets(document: Any, text: str, offset: int,
                        targets: list[tuple[str, str]]) -> list[Any]:
        if any(kind == "name" for kind, _span in targets):
            name_calls[document.name] += 1
        return shipped_targets(document, text, offset, targets)

    headings: collections.Counter[str] = collections.Counter()
    shipped_sections = dp.sections

    def counted_sections(text: str) -> list[Any]:
        found = shipped_sections(text)
        headings[current["doc"]] += len(found)
        return found

    admitted: dict[str, collections.Counter[str]] = {
        name: collections.Counter() for name in CHANNELS
    }
    shapes: dict[str, list[int]] = {}
    spans: dict[str, list[int]] = {}

    dp._line_of = watched
    dp._check_name_targets = counted_targets
    dp.sections = counted_sections
    try:
        for document, text in _corpus():
            current["doc"] = document.name
            current["text"] = text
            pointer_problems, checked_pointers, boxes = dp.check_pointers(document, text)
            link_problems, _checked_links, _generated = dp.check_links(document, text)
            _evidence_problems, checked_evidence = dp.check_evidence(document, text)
            admitted["check_evidence"][document.name] += checked_evidence
            admitted["check_pointers"][document.name] += (
                checked_pointers
                + sum(1 for problem in pointer_problems if problem.kind == "FENCE"))
            admitted["_check_quoted_name"][document.name] += boxes[dp.BOX_QUOTED_NAME]
            admitted["_check_name_targets"][document.name] += name_calls[document.name]
            admitted["check_links"][document.name] += sum(
                1 for problem in link_problems if problem.kind == "LINK")
            if _in_scope(document):
                pairs = dp._code_spans(text)
                spans[document.name] = [offset for offset, _span in pairs]
                shapes[document.name] = [offset for offset, span in pairs
                                         if dp._evidence_shape(span) is not None]
            else:
                spans[document.name] = []
                shapes[document.name] = []
        admitted["sections"] = headings
    finally:
        dp._line_of = shipped
        dp._check_name_targets = shipped_targets
        dp.sections = shipped_sections

    _CAPTURE.update({"asked": asked, "admitted": admitted, "shapes": shapes, "spans": spans})
    return _CAPTURE


_CAPTURE: dict[str, Any] = {}


def _askers() -> set[str]:
    """The functions in the shipped script that ask the family - read off the source, not here."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8", errors="replace"))
    owner = _enclosing_functions(tree)
    return {owner.get(node.lineno, "<module>") for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == FAMILY}


def _table() -> dict[str, tuple[int, int]]:
    """``asker -> (line numbers asked, items admitted)``, one row per asking function."""
    cap = _capture()
    return {name: (len(cap["asked"].get(name, [])), sum(cap["admitted"][name].values()))
            for name in sorted(_askers())}


# --------------------------------------------------------------------------- #
# The shapes the censuses below read, planted as source so the census - not this file - judges.
# --------------------------------------------------------------------------- #

_INLINE_PREFIX_COPY = '''
def sections(text):
    out = []
    for match in _HEADING.finditer(text):
        out.append(text.count("\\n", 0, match.start()) + 1)
    return out
'''


def _enclosing_functions(tree: ast.AST) -> dict[int, str]:
    """``lineno -> the def it sits in``; the outermost def wins where defs nest."""
    owner: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for child in ast.walk(node):
                if hasattr(child, "lineno"):
                    owner.setdefault(child.lineno, node.name)
    return owner


def _prefix_scans(source: str) -> list[tuple[str, int]]:
    """Every ``x.count("\\n", 0, <something>)`` in ``source``, with the def that wrote it.

    The bound is what makes it a prefix scan: a constant third argument counts a literal and is
    not this family's business.
    """
    tree = ast.parse(source)
    owner = _enclosing_functions(tree)
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "count" or len(node.args) != 3:
            continue
        first, second, third = node.args
        if not (isinstance(first, ast.Constant) and first.value == "\n"):
            continue
        if not (isinstance(second, ast.Constant) and second.value == 0):
            continue
        if isinstance(third, ast.Constant):
            continue
        found.append((owner.get(node.lineno, "<module>"), node.lineno))
    return found


def _cursor_read(text: str) -> tuple[Callable[[int], int], dict[str, int]]:
    """A forward cursor: walks only the gap, and pays a prefix count when a request goes back."""
    state = {"offset": -1, "line": 1, "chars": 0}

    def read(offset: int) -> int:
        if offset < state["offset"]:
            state["chars"] += offset
            return text.count("\n", 0, offset) + 1
        state["chars"] += max(offset - state["offset"] - 1, 0)
        state["line"] += text.count("\n", state["offset"] + 1, offset)
        state["offset"] = offset
        return state["line"]

    return read, state


def _index_read(text: str) -> tuple[Callable[[int], int], dict[str, int]]:
    """A newline index built from one pass over the text, bisected per request."""
    starts = [i for i, ch in enumerate(text) if ch == "\n"]
    state = {"chars": len(text)}

    def read(offset: int) -> int:
        return bisect.bisect_right(starts, offset - 1) + 1

    return read, state


def _replay(streams: dict[str, list[tuple[str, int, int]]], texts: dict[str, str],
            build: Callable[[str], tuple[Callable[[int], int], dict[str, int]]],
            per_document: bool) -> tuple[list[str], int]:
    """Answer every captured request with one reading; return the wrong answers and the characters."""
    instances: dict[str, tuple[Callable[[int], int], dict[str, int]]] = {}
    wrong: list[str] = []
    for caller, events in streams.items():
        for name, offset, expected in events:
            key = name if per_document else f"{caller}:{name}"
            if key not in instances:
                instances[key] = build(texts[name])
            read, state = instances[key]
            got = read(offset)
            if got != expected and len(wrong) < 4:
                wrong.append(f"{caller} {name} offset={offset} shipped={expected} got={got}")
    return wrong, sum(state["chars"] for _read, state in instances.values())


# --------------------------------------------------------------------------- #
# The legs.
# --------------------------------------------------------------------------- #

def test_the_reader_asks_one_line_number_per_item_it_admits() -> None:
    """The identity, one row per asking function: asked == admitted.

    Every admitted count comes from the shipped reader itself -- ``check_evidence``'s own
    ``checked``, ``check_pointers``'s ``checked`` plus the fence problems it emitted, the
    quoted-name box it counted, the targets its own caller handed ``_check_name_targets``, the
    link problems it returned -- so a site cannot pass by this file editing its own denominator.
    """
    uneven = {name: counts for name, counts in _table().items() if counts[0] != counts[1]}
    assert uneven == {}, f"要了行号却没判这一项的站点（请求, 承认）：{uneven}"


def test_no_line_number_is_paid_for_a_span_the_shape_throws_away() -> None:
    """The same identity as an offset set, so the discarded population has a price.

    ``check_evidence`` may ask at an offset only if that offset is one of the evidence-shaped
    spans of the same document; every other offset it asked at is a prefix scan whose answer was
    thrown away on the next line.
    """
    cap = _capture()
    assert all(own for _doc, _offset, _line, own in cap["asked"].get("check_evidence", [])), (
        "证据循环在一个不是被检文档的文本上要了行号：这条腿比的是同一份文本的偏移")
    offenders: list[tuple[str, int, int]] = []
    for name, admitted_offsets in cap["shapes"].items():
        allowed = set(admitted_offsets)
        asked = [offset for doc, offset, _line, _own in cap["asked"].get("check_evidence", [])
                 if doc == name]
        discarded = [offset for offset in asked if offset not in allowed]
        if discarded:
            offenders.append((name, len(discarded), sum(discarded)))
    assert offenders == [], f"为没进判决的跨度数了行号：(文档, 条数, 白扫的字符) {offenders[:4]}"


def test_the_discarded_population_is_real_and_the_kept_one_is_smaller() -> None:
    """The leg above only means something because most spans are thrown away.

    Counted from the same shipped predicates: the corpus has strictly more code spans than
    evidence-shaped spans, and the pinned document has both kinds.  Without this, "asked ==
    admitted" could be satisfied by a reader that admits everything.
    """
    cap = _capture()
    total_spans = sum(len(v) for v in cap["spans"].values())
    total_shapes = sum(len(v) for v in cap["shapes"].values())
    assert total_shapes < total_spans, (total_shapes, total_spans)
    pinned = "t556_pinned_evidence.md"
    assert cap["shapes"][pinned], cap["spans"][pinned]
    assert len(cap["spans"][pinned]) > len(cap["shapes"][pinned]), (
        cap["spans"][pinned], cap["shapes"][pinned])


def test_the_cold_members_are_reached_by_a_document_that_reaches_them() -> None:
    """The members the shipped corpus never touches are judged where somebody does.

    For a pinned document the asking function and the admitting channel are the same number and
    that number is at least one: an unclosed fence is asked once and reported once, a dead link is
    asked once and reported once.
    """
    cap = _capture()
    for name, asker in (("t556_pinned_fence.md", "check_pointers"),
                        ("t556_pinned_link.md", "check_links")):
        asked = [offset for doc, offset, _line, _own in cap["asked"].get(asker, []) if doc == name]
        admitted = cap["admitted"][asker][name]
        assert admitted >= 1, (name, admitted)
        assert len(asked) == admitted, (name, len(asked), admitted)


def test_the_family_is_enumerated_from_the_source_and_no_asker_is_left_unjudged() -> None:
    """Nobody may add an asking site and keep this file green by leaving it out of the table."""
    askers = _askers()
    unjudged = sorted(askers - CHANNELS)
    assert unjudged == [], f"新的要行号的人没有承认渠道可数：{unjudged}"
    assert "<module>" not in askers, sorted(askers)
    table = _table()
    for name, (asked, _admitted) in sorted(table.items()):
        assert asked > 0, f"{name} 一次都没被问过：这一行是白过的"


def test_a_channel_that_admits_items_asks_the_door_for_their_line_numbers() -> None:
    """The derived roster's own blind spot, armed on the shipped reader's counts.

    ``_askers()`` reads who calls ``_line_of``, so a member that *stops* calling it simply leaves
    the table - and a row that is not in the table cannot be uneven.  The admitted side of such a
    member is still counted by the shipped reader, so the pairing that has to hold is the other
    one: a channel that admitted items in this pass without asking the door for their line numbers
    means those numbers came from somewhere this census cannot see.  This batch landed by folding
    exactly one such copy into the helper, which is why the shape is judged rather than assumed
    away - and why the door census above is not enough on its own.
    """
    cap = _capture()
    silent = sorted(name for name in CHANNELS
                    if sum(cap["admitted"][name].values()) > 0 and name not in _askers())
    assert silent == [], f"承认了项目却没问行号的名字（行号另有出处）：{silent}"


def test_the_prefix_count_has_one_door_and_the_scan_charges_a_second_one() -> None:
    """``_line_of`` is the only place the prefix scan is written.

    A copy outside the helper is invisible to every measurement that watches the helper, so a
    change of reading would fix every site that goes through the door and quietly leave the copy
    behind.  The census that forbids the copy is shown to be capable of finding one, by running
    the same scan over a planted copy.
    """
    source = SCRIPT.read_text(encoding="utf-8", errors="replace")
    outside = [site for site in _prefix_scans(source) if site[0] != FAMILY]
    assert outside == [], outside
    charged = _prefix_scans(_INLINE_PREFIX_COPY)
    assert [name for name, _line in charged] == ["sections"], charged


def test_the_answer_is_still_bounded_so_the_whole_document_roster_still_excludes_it() -> None:
    """Batch 537's boundary, re-read here rather than assumed.

    ``_line_of`` must stay "count up to the offset".  The moment it walks the whole text it is the
    same charge as a per-item whole-document rescan, and the roster in ``M555_FILE`` -- which
    derives its scanners from the reader -- has to take it.  That rewrite belongs to the batch
    that changes the reading, not to this one.
    """
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8", errors="replace"))
    definition = next(node for node in tree.body
                      if isinstance(node, ast.FunctionDef) and node.name == FAMILY)
    bounded = [node for node in ast.walk(definition)
               if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
               and node.func.attr == "count" and len(node.args) == 3
               and isinstance(node.args[1], ast.Constant) and node.args[1].value == 0
               and isinstance(node.args[2], ast.Name)]
    assert len(bounded) == 1, bounded


def test_the_two_alternative_readings_answer_every_request_the_shipped_one_answers() -> None:
    """The deferred choice, priced without asserting a price.

    A forward cursor and a newline index - built per asking site, and built once per document --
    replay the captured request streams in request order.  All three agree on every request, and
    their character bills come out ordered, which is the only claim this leg keeps.

    Only requests made on the checked document's own text are replayed: an index built for one
    document cannot answer offsets read out of another, and the leg below names who asks in that
    other way rather than letting the exception disappear from the count.
    """
    cap = _capture()
    texts = {document.name: text for document, text in _corpus()}
    foreign = {caller for caller, events in cap["asked"].items()
               if any(not own for _doc, _offset, _line, own in events)}
    assert foreign <= {"sections"}, sorted(foreign)
    streams = {caller: [(name, offset, line) for name, offset, line, own in events if own]
               for caller, events in cap["asked"].items()}
    shipped_chars = sum(offset for events in streams.values() for _n, offset, _l in events)
    bills: dict[str, int] = {}
    for label, build, per_document in (("cursor", _cursor_read, False),
                                       ("index-per-site", _index_read, False),
                                       ("index-per-document", _index_read, True)):
        wrong, chars = _replay(streams, texts, build, per_document)
        assert wrong == [], (label, wrong)
        bills[label] = chars
    assert (bills["index-per-document"] < bills["cursor"] < bills["index-per-site"]
            < shipped_chars), (bills, shipped_chars)


def test_the_explanation_of_the_prefix_charge_drops_its_unmeasured_price() -> None:
    """M8-T555's own file priced this charge by hand, and a hand-copied reading has no reader.

    The paragraph still owes the boundary -- a prefix charge is a *separate* charge, which is the
    claim the leg above re-reads -- but it has to point at a leg that measures the size instead of
    at microsecond and second figures nobody re-ran.
    """
    text = (REPO_ROOT / "tests" / M555_FILE).read_text(encoding="utf-8", errors="replace")
    for stale in ("39.7", "24.8 s"):
        assert stale not in text, stale
    assert THIS_FILE in text, "改说明的批次没把量它的人点名"


def test_the_repaired_sites_say_why_the_answer_comes_after_the_filter() -> None:
    """The law lives with the code and names the leg that reads it.

    Both repaired loops used to ask first and admit second; a reader of either should learn from
    the function itself which order is the rule, and where the rule is judged.
    """
    for function in (dp.check_evidence, dp._check_name_targets):
        doc = function.__doc__ or ""
        assert "admits" in doc, function.__name__
        assert THIS_FILE in doc, function.__name__
