"""M8-T555: a per-item answer may not re-run a whole-document ruler.

The charge is a *cost*, and the cost killed the repository's own evidence.  ``tests/
test_the_two_readers_share_one_fence_ruler.py`` answers "is this offset inside a closed
fence?" once per inline code span, and until this batch the answer called
``_fence_blocks(text)`` again for every span.  Measured on the shipped ROADMAP (2,974,217
bytes, 37,226 lines, 26,041 code spans): one whole-document fence scan costs ~43 ms, so the
leg costs ~1,122 s where the same loop with the ruler read once per document costs ~0.16 s.
The conftest stack dump in ``Temp/t543_doc536b.log`` shows it running 1,029.1 s and then
being stopped by the suite's own 900 s hang limit *inside* ``scripts/doc_pointers.py:503`` -
so an evidence gate went red for a load reason and said nothing about any citation, while
``offenders == []`` says the verdict it was protecting had not changed at all.

The repair is not a faster regex; it is *who buys the ruler*.  So the gate below is a census
over the repository's own source, and the roster of scanners is **derived from the shipped
reader** rather than typed out here: renaming a scanner, adding one, or handing a document to
one inside a loop over that scanner's own results all change what the census reports, and none
of those can pass by editing a list in this file.

One boundary, disclosed rather than hidden.  ``_line_of`` also answers per item by scanning
``text``, but only the prefix up to the offset (``text.count("\\n", 0, offset)``), so its price
grows with how far into the document an item sits rather than with the document.  It is a
different charge at a different size, so it lives in its own roster and its own leg, and
``test_the_prefix_line_answer_is_a_separate_charge_and_is_named_as_one`` keeps that split on the
record instead of letting a narrow roster claim the repository is clean.  The size of that
charge is not quoted here, because a reading copied into this paragraph has no reader that
re-runs it: the family is measured from the shipped reader's own calls - requests, admissions
and the bill for the requests thrown away - by ``test_a_line_number_is_asked_only_for_an_item_the_reader_admits.py``.
"""

from __future__ import annotations

import ast
import importlib.util
import pathlib
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "doc_pointers.py"

#: The population the census walks.  A glob, not ``git ls-files``: pytest collects the
#: filesystem, and an untracked scratch file can hold the very loop being charged.
POPULATION_ROOTS = ("tests", "scripts", "minicc")

#: Calls whose cost is a function of the text they are handed.  ``count`` / ``find`` are
#: absent on purpose - handed a bound they walk a prefix, which is the other charge.
WHOLE_TEXT_METHODS = frozenset({"finditer", "findall", "fullmatch", "search", "match", "sub",
                                "subn", "split", "splitlines"})

#: The scanners this defect family spans, as a *floor* on the derived roster.
CHARGED_SCANNERS = ("_fence_blocks", "_blank_fences", "_mask_code", "_code_spans")

#: The disclosed neighbouring charge - prefix-bounded, so outside the whole-document roster.
PREFIX_SCANNER = "_line_of"


def _load(name: str = "minicc_doc_pointers_t555") -> Any:
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # scripts/ is not a package; @dataclass(slots=True) resolves annotations through
    # sys.modules, so the module has to be registered before it is executed.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


dp = _load()
#: The reader owns the rulers, so the reader is where the roster is read from.
READER_SCANNERS = frozenset()


def _population() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for root in POPULATION_ROOTS:
        files += [p for p in (REPO_ROOT / root).rglob("*.py") if "__pycache__" not in p.parts]
    return sorted(set(files))


def _parse(path: pathlib.Path) -> ast.Module | None:
    """Parsed once per file and kept: a census that re-reads the tree for every roster it tries
    is buying the ruler per item, which is the very shape it charges."""
    if path not in _TREE_CACHE:
        _TREE_CACHE[path] = None
        try:
            _TREE_CACHE[path] = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            pass
    return _TREE_CACHE[path]


_TREE_CACHE: dict[pathlib.Path, ast.Module | None] = {}


def _callee(call: ast.Call) -> str:
    node: Any = call.func
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _walks_one_of(call: ast.Call, names: set[str], scanners: set[str]) -> str | None:
    """The name this call walks whole, if it walks one of ``names`` - else ``None``.

    Argument position is a property of the callee, not of the call site: a compiled pattern
    takes the text first, ``re.sub`` takes it last, ``str.splitlines`` takes it as its
    receiver, and a scanner delegates by handing its own parameter on.
    """
    callee = _callee(call)
    if callee in ("finditer", "findall", "fullmatch", "search", "match") and call.args:
        walked = call.args[-1]
    elif callee in ("sub", "subn") and len(call.args) >= 3:
        walked = call.args[2]
    elif callee in ("split", "splitlines") and not call.args and isinstance(call.func, ast.Attribute):
        walked = call.func.value
    elif callee in scanners and call.args:
        walked = call.args[0]
    else:
        return None
    if isinstance(walked, ast.Name) and walked.id in names:
        return walked.id
    return None


def derived_scanners(tree: ast.Module) -> set[str]:
    """Module-level defs whose cost is a function of the whole document they are handed.

    Two rules, closed to a fixpoint: a def that walks one of its own parameters with a
    whole-text method, or a def that hands a parameter unchanged to another such def.
    """
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    scanners: set[str] = set()
    for _round in range(len(functions) + 2):
        grown = set(scanners)
        for fn in functions:
            params = {argument.arg for argument in fn.args.args} | {
                argument.arg for argument in fn.args.kwonlyargs}
            for call in ast.walk(fn):
                if isinstance(call, ast.Call) and _walks_one_of(call, params, scanners) is not None:
                    grown.add(fn.name)
        if grown == scanners:
            return scanners
        scanners = grown
    return scanners


def charged_helpers(tree: ast.Module, scanners: set[str]) -> dict[str, set[str]]:
    """``helper -> the parameter names it re-scans``, so a loop calling it is charged too.

    This is the reach the shipped defect actually had: the corpus leg's loop called
    ``_block_of``, and ``_block_of`` was the one re-running the ruler.  A census that looked only
    at direct calls would have charged nothing and reported a clean repository.
    """
    table: dict[str, set[str]] = {}
    functions = [node for node in ast.walk(tree)
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for _round in range(len(functions) + 2):
        grown: dict[str, set[str]] = {key: set(value) for key, value in table.items()}
        for fn in functions:
            params = {argument.arg for argument in fn.args.args} | {
                argument.arg for argument in fn.args.kwonlyargs}
            for call in ast.walk(fn):
                if not isinstance(call, ast.Call):
                    continue
                callee = _callee(call)
                if callee not in scanners and callee not in table:
                    continue
                for argument in call.args:
                    if isinstance(argument, ast.Name) and (
                            argument.id in params or argument.id in table.get(callee, set())):
                        grown.setdefault(fn.name, set()).add(argument.id)
        if grown == table:
            return table
        table = grown
    return table


def _applied(node: ast.AST, table: dict[str, set[str]], scanners: set[str]) -> list[tuple[str, str]]:
    """Every ``(callable, name)`` this expression re-scans, reaching through charged helpers."""
    found: list[tuple[str, str]] = []
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        callee = _callee(call)
        if callee not in scanners and callee not in table:
            continue
        for argument in call.args:
            if isinstance(argument, ast.Name):
                found.append((callee, argument.id))
    return found


def _sites(tree: ast.Module, label: str, scanners: set[str]) -> list[dict[str, Any]]:
    """Loops that iterate a whole-document scan of ``X`` and answer each item with a scan of ``X``."""
    table = charged_helpers(tree, scanners)
    sites: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.For, ast.AsyncFor)):
            continue
        for bought_by, bought_name in _applied(node.iter, table, scanners):
            for body_node in node.body:
                for callee, rescanned in _applied(body_node, table, scanners):
                    if rescanned == bought_name and callee != bought_by:
                        sites.append({"file": label, "line": node.lineno, "name": rescanned,
                                      "loop_over": bought_by, "answered_by": callee,
                                      "through_helper": callee in table})
    return sites


def census(paths: list[pathlib.Path], extra_scanners: set[str] = frozenset()) -> list[dict[str, Any]]:
    """Run the walk over the tree.  ``extra_scanners`` is how the disclosed prefix charge stays
    enumerated: the same walk, with ``_line_of`` added, reports the family left for the next batch.

    Memoised per roster, because the census reading its own tree twice is the same bill this
    batch is closing.
    """
    key = frozenset(extra_scanners)
    if key in _CENSUS_CACHE:
        return _CENSUS_CACHE[key]
    reader = _parse(SCRIPT)
    assert reader is not None, SCRIPT
    base = derived_scanners(reader) | key
    sites: list[dict[str, Any]] = []
    for path in paths:
        tree = _parse(path)
        if tree is None:
            continue
        label = path.relative_to(REPO_ROOT).as_posix()
        sites += _sites(tree, label, base | derived_scanners(tree))
    _CENSUS_CACHE[key] = sites
    return sites


_CENSUS_CACHE: dict[frozenset[str], list[dict[str, Any]]] = {}


def _snippet_sites(source: str) -> list[dict[str, Any]]:
    """The census over an in-memory file, so the census is judged against shapes it owns."""
    reader = _parse(SCRIPT)
    assert reader is not None, SCRIPT
    tree = ast.parse(source)
    return _sites(tree, "_t555_snippet.py", derived_scanners(reader))


# --------------------------------------------------------------------------- #
# The shapes, written as source because the census - not this file - does the judging.
# --------------------------------------------------------------------------- #

_RESANNING_SHAPE = '''
def _block_of(text, offset):
    for start, end in _fence_blocks(text)[0]:
        if start <= offset < end:
            return (start, end)
    return None


def leg(text):
    hits = []
    for offset, span in _code_spans(text):
        if _block_of(text, offset) is not None:
            hits.append(span)
    return hits
'''

_HOISTED_SHAPE = '''
def _block_of(ranges, offset):
    low, high = 0, len(ranges)
    while low < high:
        middle = (low + high) // 2
        if ranges[middle][0] <= offset:
            low = middle + 1
        else:
            high = middle
    if low == 0:
        return None
    start, end = ranges[low - 1]
    return (start, end) if offset < end else None


def leg(text):
    ranges = _fence_blocks(text)[0]
    hits = []
    for offset, span in _code_spans(text):
        if _block_of(ranges, offset) is not None:
            hits.append(span)
    return hits
'''

_LINEAR_OVER_HOISTED_RANGES = '''
def _block_of(ranges, offset):
    for start, end in ranges:
        if start <= offset < end:
            return (start, end)
    return None


def leg(text):
    ranges = _fence_blocks(text)[0]
    hits = []
    for offset, span in _code_spans(text):
        if _block_of(ranges, offset) is not None:
            hits.append(span)
    return hits
'''

_TWO_HOP_SHAPE = '''
def _inner(text):
    return _fence_blocks(text)[0]


def _answer(text, offset):
    for box in _inner(text):
        if box[0] <= offset < box[1]:
            return box
    return None


def leg(text):
    hits = []
    for offset, span in _code_spans(text):
        if _answer(text, offset) is not None:
            hits.append(span)
    return hits
'''


def test_no_loop_in_the_repository_answers_an_item_by_re_running_a_whole_document_ruler() -> None:
    """The census over the tree - the leg batch 537 lands green and every later batch keeps green.

    The population is pinned from the same walk that produces the verdict, so a census that
    reached no files cannot read as a clean repository.
    """
    files = _population()
    assert len(files) > 400, f"普查没有走到仓库：{len(files)} 个文件"
    sites = census(files)
    assert sites == [], (
        f"逐项重扫整档的循环 {len(sites)} 处："
        f"{[(site['file'], site['line'], site['loop_over'], site['answered_by']) for site in sites[:6]]}"
    )


def test_the_census_charges_the_shape_it_claims_and_clears_the_repaired_one() -> None:
    """A census reporting nothing must be shown to be capable of reporting something.

    Both directions in one leg, the way M8-T521 pinned its ruler: the resanning shape is
    charged, and the shape that differs only in *who buys the ruler* is not.  Without the second
    half, a census broken by its own walk would be indistinguishable from a repaired repository.
    """
    charged = _snippet_sites(_RESANNING_SHAPE)
    assert [site["answered_by"] for site in charged] == ["_block_of"], charged
    assert [site["name"] for site in charged] == ["text"], charged
    assert charged[0]["through_helper"] is True, charged
    assert _snippet_sites(_HOISTED_SHAPE) == [], _snippet_sites(_HOISTED_SHAPE)
    # O(spans x blocks) over a hoisted ruler is not the charge: the ruler was bought once, and
    # 126 blocks is a different bill from 2.97 MB.  Charging it would be the gate lying.
    assert _snippet_sites(_LINEAR_OVER_HOISTED_RANGES) == [], _snippet_sites(_LINEAR_OVER_HOISTED_RANGES)


def test_the_census_reaches_a_chain_of_helpers_that_pass_the_document_along() -> None:
    """The shipped defect hid one hop deep, so a direct-calls-only census would have missed it.

    ``_TWO_HOP_SHAPE`` is that form: the loop calls a helper, the helper calls a second helper,
    and only the innermost one re-runs the ruler.  Charging it takes a fixpoint over helper
    bodies, which is what this leg arms.
    """
    charged = _snippet_sites(_TWO_HOP_SHAPE)
    assert charged, "两跳的重扫没被认出来：名册只看得见直调，正文里的循环一藏就藏过了门"
    assert {site["answered_by"] for site in charged} & {"_answer", "_inner"}, charged


def test_the_scanner_roster_is_derived_and_covers_every_document_walker_it_needs() -> None:
    """Nobody may shrink the census by editing a list - the roster is read off the reader.

    The four names are the floor: they are the scanners this defect family spans, and a rename
    or a deletion that drops one of them out of the derived set goes red here rather than making
    the census quietly blind.
    """
    reader = _parse(SCRIPT)
    assert reader is not None, SCRIPT
    scanners = derived_scanners(reader)
    missing = sorted(name for name in CHARGED_SCANNERS if name not in scanners)
    assert missing == [], (f"名册不再认得这些整档扫描器：{missing}；现存 {sorted(scanners)}")
    assert PREFIX_SCANNER not in scanners, sorted(scanners)


def test_the_prefix_line_answer_is_a_separate_charge_and_is_named_as_one() -> None:
    """The roster's boundary, read off the shipped source rather than assumed, and enumerated.

    ``_line_of`` walks ``text`` per item too, but only up to the offset, so its cost is a prefix
    rather than a document; the shipped reader asks it inside four loops.  That is a real charge
    and it is *not* what killed the leg, so it is disclosed here - with its sites counted -
    instead of being folded into a roster that could then claim the repository is clean.
    """
    reader = _parse(SCRIPT)
    assert reader is not None, SCRIPT
    definition = next(fn for fn in reader.body
                      if isinstance(fn, ast.FunctionDef) and fn.name == PREFIX_SCANNER)
    bounded = [
        call for call in ast.walk(definition)
        if isinstance(call, ast.Call) and _callee(call) == "count" and len(call.args) == 3
        and isinstance(call.args[1], ast.Constant) and call.args[1].value == 0
        and not isinstance(call.args[2], ast.Constant)
    ]
    assert bounded, (
        f"{PREFIX_SCANNER} 不再是「数到 offset 为止」的前缀扫描：它现在和整档扫描同价，"
        "就必须进上面那个派生名册，这条腿正是改判的地方"
    )
    prefix_sites = census(_population(), extra_scanners={PREFIX_SCANNER})
    in_reader = sorted({(site["line"], site["answered_by"], site["name"])
                        for site in prefix_sites if site["file"] == "scripts/doc_pointers.py"})
    assert len(in_reader) >= 4, in_reader
    assert any(answered == PREFIX_SCANNER for _line, answered, _name in in_reader), in_reader
    assert {name for _line, _answered, name in in_reader} == {"text"}, in_reader
    whole = census(_population())
    assert len(prefix_sites) > len(whole), (len(prefix_sites), len(whole))
