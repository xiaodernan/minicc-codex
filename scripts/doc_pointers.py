"""Check that every cross-reference in the project's markdown actually lands.

Why this exists: M8-T34's roadmap row said ``见下方「第十八批 M8-T34」``, and the
section named there is the M8 exit-criteria record, which has no such
subsection. A pointer to a paragraph that does not exist is the documentation
twin of a constant that no code reads (M8-T29) — it looks like evidence while
leading nowhere. Worse, M8-T35 rewrote that row to *describe* the defect and
re-emitted the same broken pointer inside the new sentence, which is precisely
what a human proofreading their own text does not catch.

Two classes are checked, both mechanically:

``pointer``
    ``见``/``参见`` + an optional directional word (下方, 上方, 文末, 本节, …) + an
    optional 「…」 span — but **only when the span names a locator** (``第N批``,
    ``第N节``, ``附录 X``) or an id (``M8-T34``, ``M4-3``, ``P0-1``). Chinese
    prose is full of ``见`` that is merely a suffix (可见, 意见, 预见, 见证, 见收益),
    so the marker alone cannot harvest references; requiring an id-shaped token
    is what makes the extraction precise. Every marker still lands in exactly one
    printed box (see ``POINTER_BOXES``), because "this pointer names no locator"
    was one opaque integer covering three different things — a word-internal 见, a
    citation another reader already resolves, and a real pointer that names a place
    by nickname (``口径见下方注记``) and stays unchecked.
    A locator must resolve to a heading, and any id in the same pointer must be
    **declared** inside that locator's section — as a heading or as a table row's
    label cell, not merely mentioned. Mentioning cannot work: 「见下方「第十八批
    M8-T34」」 itself spells the id out, so "does the id appear in the section?"
    would be answered yes by the pointer. Naming both a section and an id is a
    claim about where that id is *recorded*, and that is the claim M8-T34 got
    wrong.

``link``
    ``[text](target)`` with a non-URL target must resolve **inside what git
    tracks**. A target git ignores is a run's own output, so it is counted
    separately as ``generated`` rather than reported as broken; a target that
    exists only on this machine — present, untracked, not ignored — is red, which
    is the dangling link the author is the last person able to see.

Counts for both are printed, and ``--check`` fails when the inventory is
suspiciously small too: an empty harvest means the extractor went blind, which
is the same failure mode as a coverage denominator that quietly shrinks
(M8-T35's 34 → 31 incident).
"""

from __future__ import annotations

import argparse
import ast
import difflib
import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DOCS = tuple(sorted((REPO_ROOT / "docs").glob("*.md"))) + (REPO_ROOT / "README.md",)

#: A document that claims to be cross-referenced must yield at least this many
#: checkable pointers/links; below the floor the tool reports an inventory
#: problem instead of a clean run. The floors sit deliberately *below* what the
#: current documents hold (roadmap: 30 pointers / 2 links, README: 1 / 7) so
#: they trip only when an extractor goes blind, not when prose is reworded.
MIN_POINTERS = {"docs/ROADMAP_TO_PRODUCT.md": 15}
MIN_LINKS = {"docs/ROADMAP_TO_PRODUCT.md": 1, "README.md": 3}

_POINTER = re.compile(
    r"(?:见|参见)\s*(下方|上方|文末|上一段|下一段|上一行|下一行|本节|本批末尾|该批)?\s*[「『]([^」』\n]{1,60})[」』]"
    r"|(?:见|参见)\s*(下方|上方|文末|上一段|下一段|上一行|下一行|本节|本批末尾|该批)?([^」『\n，。；：|`]{0,60})"
)
#: What a citation may start with, right after the marker. Longer alternatives come
#: first because ``re`` keeps the leftmost match: 下方 before 下.
_CITATION_HEAD = re.compile(
    r"^(?:下方|上文|下文|上方|上一段|下一段|上一行|下一行|本批末尾|本节|本批|该批|文末|上表|下表|下|上|第|附录"
    r"|[「『\[`]|[MP]\d|[A-Za-z0-9_.\-]+/)"
)
#: A section number may be written either way, and both spellings occur in this
#: repository pointing at real things: 「第十二节」 and 「证据见交付说明第8节」. Reading
#: only the Chinese one left two live pointers in the word-interior box — never checked,
#: never reported as unchecked-by-design. ``## 8. 继续实施`` is a heading that *answers*
#: 第8节, so the pair is checkable once the digit is admitted on both sides.
_NUM = r"(\d+|[一二三四五六七八九十]+)"
_SECTION = re.compile(rf"第{_NUM}节")
_BATCH = re.compile(rf"第{_NUM}批(续二|续)?")
_APPENDIX = re.compile(r"附录\s*([A-Z])")
#: ``\b`` treats Chinese as a word character, so ``见下方M8-T26`` — an id glued
#: straight onto the prose, with no space — had no boundary in front of it and was
#: invisible to this pattern: the pointer was silently never checked. The lookarounds
#: spell out the only boundary wanted here: an id is not part of a longer ASCII word
#: (``XM8-T34`` stays unmatched), and CJK on either side is fine.
_ID = re.compile(r"(?<![A-Za-z0-9_])([MP]\d+(?:-[A-Z]?\d+|\.\d+)?)(?![A-Za-z0-9_])")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.M)
_ROW = re.compile(r"^\|(.+)$", re.M)
_LINK = re.compile(r"\[([^\]\n]{1,120})\]\(([^)\s]{1,160})\)")
_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

#: Every 「见」 marker is sorted into exactly one of these, and the counts are
#: printed per box. Before M8-T39 the tool reported one integer — "N spans name no
#: locator" — which mixed 65 word-internal 见 (可见, 意见, 见证: not references at
#: all), 9 pointers another reader already resolves, and ~15 real pointers that name
#: a place without a checkable locator (「口径见下方注记」). Those three need different
#: responses, so they must not share a number — and one of them was not merely
#: skipped: 「可见价值低于 M6–M8 任何一项」 *passed* as a checked pointer, because both
#: ids exist somewhere in the file. A box that can hold a fabricated pointer is worse
#: than a box that admits it guards nothing.
BOX_CHECKED = "checked"
BOX_NO_LOCATOR = "citation-without-locator"
BOX_LINK_TEXT = "carried-by-link-reader"
BOX_CODE_SPAN = "carried-by-evidence-reader"
#: A citation whose gap holds a file name the evidence reader will not parse (bare
#: ``config.py:331-338``, or a path under an ignored directory). The pointer reader
#: answers for these itself instead of booking them as someone else's.
BOX_CODE_NAME = "code-span-names-a-file"
BOX_PATH = "path-in-prose"
BOX_WORD = "word-interior"
POINTER_BOXES = (
    BOX_CHECKED,
    BOX_NO_LOCATOR,
    BOX_LINK_TEXT,
    BOX_CODE_SPAN,
    BOX_CODE_NAME,
    BOX_PATH,
    BOX_WORD,
)


@dataclass(frozen=True, slots=True)
class Section:
    """A heading plus the text it owns, up to the next heading of any level."""

    level: int
    title: str
    line: int
    body: str


@dataclass(frozen=True, slots=True)
class Problem:
    kind: str
    document: str
    line: int
    detail: str

    def __str__(self) -> str:
        return f"{self.kind} {self.document}:{self.line}: {self.detail}"


@dataclass(frozen=True, slots=True)
class Stats:
    pointers: int
    markers: int
    boxes: dict[str, int]
    links: int
    evidence: int = 0
    prose_paths: int = 0
    links_generated: int = 0


def sections(text: str) -> list[Section]:
    """Every heading with the span beneath it, until the next heading."""
    found = list(_HEADING.finditer(text))
    out: list[Section] = []
    for index, match in enumerate(found):
        end = found[index + 1].start() if index + 1 < len(found) else len(text)
        out.append(
            Section(
                level=len(match.group(1)),
                title=match.group(2).strip(),
                line=text.count("\n", 0, match.start()) + 1,
                body=text[match.end() : end],
            )
        )
    return out


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _numeral(word: str) -> int | None:
    """Read a section number written either way: 十二, or 8."""
    if re.fullmatch(r"\d+", word):
        return int(word)
    if word in _DIGITS:
        return _DIGITS[word]
    if word == "十":
        return 10
    match = re.fullmatch(r"十([一二三四五六七八九])?", word)
    if match:
        return 10 + _DIGITS.get(match.group(1) or "", 0)
    match = re.fullmatch(r"([一二三四五六七八九])十([一二三四五六七八九])?", word)
    if match:
        return _DIGITS[match.group(1)] * 10 + _DIGITS.get(match.group(2) or "", 0)
    return None


def _numbered_headings(headings: list[Section]) -> dict[int, Section]:
    """Map ``N`` to the level-2 heading that declares itself section N.

    Two spellings are in use here: the roadmap writes ``## 四、明确不做什么`` while
    prose says 「第四节」, and the delivery record writes ``## 8. 继续实施`` while prose
    says 「第8节」. Both have to be tied to their number before a section pointer means
    anything; a heading that declares no number cannot be pointed at.
    """
    out: dict[int, Section] = {}
    for section in headings:
        if section.level != 2:
            continue
        match = re.match(r"^([一二三四五六七八九十]+|\d+)[.、]", section.title)
        if match:
            numeral = _numeral(match.group(1))
            if numeral is not None:
                out.setdefault(numeral, section)
    return out


def _batch_labels(headings: list[Section]) -> dict[str, Section]:
    """Every ``第N批`` a heading declares about itself, keyed by its exact label.

    Built by running the same matcher over the titles the pointers name, so a
    heading that never says which batch it is cannot be pointed at — and 「第十五批
    续」 and 「第十五批续二」 stay two different sections.
    """
    out: dict[str, Section] = {}
    for section in headings:
        for match in _BATCH.finditer(section.title):
            out.setdefault(f"第{match.group(1)}批{match.group(2) or ''}", section)
    return out


def _id_registry(scope_text: str) -> set[str]:
    """Ids the scope *declares*: headings and the label cell of a table row.

    Reading an id straight out of the prose instead cannot work — 「见 M8-T999」
    mentions M8-T999, so "does this id appear in the document?" is answered yes
    by the pointer itself. A pointer to a row is a claim that a row exists, so
    only structural positions count as evidence.
    """
    declared = [match.group(2) for match in _HEADING.finditer(scope_text)]
    declared += [row.split("|")[0] for row in _ROW.findall(scope_text)]
    ids: set[str] = set()
    for line in declared:
        ids.update(_ID.findall(line))
    return ids


def _sentence(text: str, offset: int) -> str:
    """The sentence around a pointer, used to find a *named* target document."""
    start = max(text.rfind("。", 0, offset), text.rfind("\n", 0, offset)) + 1
    end = text.find("。", offset)
    return text[start : len(text) if end < 0 else end]


def _named_documents(text: str, offset: int) -> list[Path]:
    """Markdown files the sentence around ``offset`` names, and that exist."""
    found: list[Path] = []
    for name in re.findall(r"([\w.\-]+\.md)", _sentence(text, offset)):
        direct = REPO_ROOT / name
        path = direct if direct.exists() else REPO_ROOT / "docs" / name
        if path.exists() and path not in found:
            found.append(path)
    return found


def _cross_document_sections(text: str, offset: int, numeral: int) -> list[Section]:
    """Resolve ``第N节`` inside every document the sentence names explicitly.

    ``复核命令见审核文档第十二节`` cannot be checked: "审核文档" is not a file a
    tool can find, and it happens to be the one document whose 第十二节 does
    exist. ``见 docs/X.md 第N节`` is checkable, so that is the form the gate
    accepts.
    """
    found: list[Section] = []
    for path in _named_documents(text, offset):
        target = _numbered_headings(sections(path.read_text(encoding="utf-8"))).get(numeral)
        if target is not None:
            found.append(target)
    return found


def _mask_code(text: str) -> str:
    """Blank out fenced blocks and inline code, keeping every offset in place.

    A pointer written *inside* a code span is a quotation, not a reference: this
    README illustrates the M8-T34 defect by writing ``见「第十八批 M8-T34」`` in
    backticks, and harvesting that as a claim would make the gate red for the
    wrong reason. Offsets are preserved so a hit still maps onto the original.
    """
    blanked = re.sub(r"```.*?```", lambda m: " " * len(m.group(0)), text, flags=re.S)
    return re.sub(r"`[^`\n]*`", lambda m: " " * len(m.group(0)), blanked)


def _locator(span: str) -> bool:
    """Does this span name anything the tool can resolve — a section, batch, appendix or id?"""
    return bool(_BATCH.search(span) or _SECTION.search(span) or _APPENDIX.search(span) or _ID.findall(span))


def _gap_targets(gap: str) -> list[tuple[str, str]]:
    """``(kind, span)`` for each code span in a citation gap that points at something.

    ``evidence`` is a shape the evidence reader parses on its own. ``name`` is the
    case M8-T41 found: a bare file name (``config.py:331-338``, ``test_x.py``) or a
    path under a directory git ignores, which the evidence reader *deliberately*
    skips — so the promise in ``carried-by-evidence-reader`` was never collected.
    Anything else in a gap (``answer``, ``task_search``) is a field or identifier,
    not a target, and must not be filed as if another reader had it.
    """
    targets: list[tuple[str, str]] = []
    for match in _CODE_SPAN.finditer(gap):
        span = match.group(1).strip()
        if _evidence_shape(span) is not None:
            targets.append(("evidence", span))
        elif _NAME_REF.match(span):
            targets.append(("name", span))
    return targets


def _link_target(match: re.Match[str]) -> str:
    return match.group(2).split("#")[0].strip()


def _link_judged(match: re.Match[str]) -> bool:
    """Does the link reader form a verdict about this link at all?

    ``check_links`` skips an empty target, an in-page anchor and an external URL: those
    are not claims about this repository, so nobody checks them and a citation landing on
    one cannot be booked as someone else's work. This is the *only* copy of that skip
    list — the link reader consults it too, so the two sides cannot drift.
    """
    target = _link_target(match)
    return bool(target) and not target.startswith(("http://", "https://", "mailto:"))


def _region_has_judged_link(region: str) -> bool:
    """``carried-by-link-reader`` is a promise that another reader answers for this
    marker, so the test is that reader's own grammar over the region it actually sees —
    not merely "a bracket is somewhere in the sentence".
    """
    return any(_link_judged(match) for match in _LINK.finditer(region))


def _pointer_box(gap: str, span: str, region: str) -> str:
    """Sort one 「见」 marker into the account.

    ``gap`` is the *unmasked* text between the marker and where the harvest began;
    offsets survive masking, so it says whether a locator was there all along and got
    blanked out (a code span, which is either handed to the evidence reader or resolved
    here — see ``_gap_targets``) or never was. ``region`` is the *masked* text the marker
    actually covers, which is what the link reader sees when it decides whether a link
    there is one it judges.

    A locator-shaped span still has to be a *citation*: 「可见价值低于 M6–M8 任何一项」
    contains two ids and is 可见 plus unrelated prose, so an id alone does not make a
    pointer — it has to sit where a cited place would. A span that names a section,
    batch or appendix is exempt from that test, because 第N节/第N批 are place-words a
    sentence does not trip over by accident: 「复核命令见审核文档第十二节」 is a real
    pointer even though 见 is glued to a noun, and it is the one shape whose file name
    the rule below still requires.
    """
    has_place = bool(_BATCH.search(span) or _SECTION.search(span) or _APPENDIX.search(span))
    cited = bool(span) and (has_place or _CITATION_HEAD.match(span) is not None)
    if cited and _locator(span):
        return BOX_CHECKED
    kinds = {kind for kind, _ in _gap_targets(gap)}
    if "evidence" in kinds:
        return BOX_CODE_SPAN
    if "name" in kinds:
        return BOX_CODE_NAME
    if _CODE_SPAN.search(gap):
        # A citation pointing at a field or a flag (「见 `answer`」) is a real pointer
        # whose target has no locatable shape. It belongs in the same open account as
        # 「口径见下方注记」, never in 「word-interior」, whose meaning is "not a reference".
        return BOX_NO_LOCATOR
    if _region_has_judged_link(region):
        return BOX_LINK_TEXT
    if "[" in gap or span.startswith("["):
        # A bracket that is not a link the reader judges (「见 [待定]」「见 [说明](a b.md)」,
        # an in-page anchor, an external URL) is still a citation pointing somewhere the
        # tool cannot look up. It must not buy its way into the hand-off box, and it must
        # not land in 「word-interior」 either — that box means "not a reference".
        return BOX_NO_LOCATOR if cited else BOX_WORD
    if cited and "/" in span:
        return BOX_PATH
    if cited:
        return BOX_NO_LOCATOR
    # Both halves of this box are real and neither is a reference this tool can look
    # up: 可见收益 (a suffix) and 见交付说明第8节 (a verb pointing at a nickname).
    return BOX_WORD


def _pointer_spans(text: str) -> list[tuple[int, str, str, list[tuple[str, str]]]]:
    """(offset, span, box, gap targets) for every ``见`` marker, quote-delimited forms first."""
    masked = _mask_code(text)
    out: list[tuple[int, str, str, list[tuple[str, str]]]] = []
    for match in _POINTER.finditer(masked):
        after = match.start() + (2 if masked.startswith("参见", match.start()) else 1)
        if (quoted := match.group(2)) is not None:
            gap = text[after : match.start(2)]
            span = quoted.strip()
            out.append(
                (
                    match.start(),
                    span,
                    _pointer_box(gap, span, masked[after : match.end()]),
                    _gap_targets(gap),
                )
            )
            continue
        direction = match.group(3) or ""
        span = f"{direction}{match.group(4) or ''}".strip()
        # The gap ends where the harvest ended, not where the match ended: the span
        # itself is *part of* the match, and asking it whether it holds a backtick
        # would file every 可见…-plus-code-further-along line as a code-span pointer.
        gap = text[after : match.start(4)]
        out.append(
            (
                match.start(),
                span,
                _pointer_box(gap, span, masked[after : match.end()]),
                _gap_targets(gap),
            )
        )
    return out


def _check_name_targets(
    document: Path, text: str, offset: int, targets: list[tuple[str, str]]
) -> list[Problem]:
    """Resolve the file names a citation points at that no other reader parses.

    A name carrying a directory is asked of the index directly; a bare name is
    satisfied by *any* tracked file with that name, because ``config.py:331-338``
    cites a location rather than an import path — the docs use that shorthand
    dozens of times, and demanding a unique match would only teach writers to type
    a directory. A name git ignores is a run's own output: still a citation, but
    judged the way the link reader judges products, not as a missing file.
    """
    line = _line_of(text, offset)
    problems: list[Problem] = []
    for kind, span in targets:
        if kind != "name":
            continue
        ref = _NAME_REF.match(span)
        assert ref is not None, span  # _gap_targets only files what it matches
        path = ref.group("path")
        if _git_ignored(path):
            continue
        if "/" in path:
            candidates = [path] if _holds(path) else []
        else:
            candidates = list(_basenames().get(path, ()))
        if not candidates:
            problems.append(
                Problem("POINTER", document.name, line, f"指针引用的 `{span}` 在仓库里没有任何同名文件")
            )
            continue
        numbering = ref.group("lines")
        if numbering and (target := REPO_ROOT / candidates[0]).exists():
            total = len(target.read_text(encoding="utf-8", errors="replace").splitlines())
            high = max(int(n) for n in re.split(r"[,\-]", numbering) if n.isdigit())
            if high > total:
                problems.append(
                    Problem(
                        "POINTER",
                        document.name,
                        line,
                        f"指针引用的 `{span}` 超出 {candidates[0]} 的行数 {total}",
                    )
                )
    return problems


def check_pointers(document: Path, text: str) -> tuple[list[Problem], int, dict[str, int]]:
    """Return problems, the number of checked pointers, and the per-box counts."""
    headings = sections(text)
    numbered = _numbered_headings(headings)
    batch_labels = _batch_labels(headings)
    problems: list[Problem] = []
    checked = 0
    boxes = {box: 0 for box in POINTER_BOXES}
    for offset, span, box, targets in _pointer_spans(text):
        boxes[box] += 1
        if box == BOX_CODE_NAME:
            problems += _check_name_targets(document, text, offset, targets)
            continue
        if box != BOX_CHECKED:
            # Every non-checked box is counted and named in the summary: that is the
            # whole point of the account. ``citation-without-locator`` is the only one
            # holding *real* pointers this tool cannot resolve, and it stays open.
            continue
        batches = list(_BATCH.finditer(span))
        secs = list(_SECTION.finditer(span))
        appendices = list(_APPENDIX.finditer(span))
        ids = _ID.findall(span)
        checked += 1
        line = _line_of(text, offset)
        target: Section | None = None
        remote: list[Section] = []
        for sec in secs:
            numeral = _numeral(sec.group(1))
            target = numbered.get(numeral) if numeral is not None else None
            if target is not None:
                continue
            found = _cross_document_sections(text, offset, numeral) if numeral is not None else []
            if found:
                remote += found  # the sentence names the file that owns the section
                continue
            problems.append(Problem("POINTER", document.name, line, f"「{span}」 指向不存在的{sec.group(0)}"))
        for batch in batches:
            token = f"第{batch.group(1)}批{batch.group(2) or ''}"
            # Exact labels only: 「第十五批续」 is not the section titled 续二, and
            # substring matching would let one pointer stand for three records.
            target = batch_labels.get(token)
            if target is None:
                problems.append(Problem("POINTER", document.name, line, f"「{span}」 指向不存在的段落「{token}」"))
        for appendix in appendices:
            found = _appendix_section(appendix.group(0), headings)
            if found is None:
                problems.append(Problem("POINTER", document.name, line, f"「{span}」 指向不存在的{appendix.group(0).strip()}"))
            else:
                target = found
        scope = f"## {target.title}\n{target.body}" if target is not None else text
        registry = _id_registry(scope)
        for section in remote:
            registry |= _id_registry(f"## {section.title}\n{section.body}")
        if target is None and not remote:
            # ``见 docs/X.md P0-1`` declares the id in the other file's heading.
            for path in _named_documents(text, offset):
                registry |= _id_registry(path.read_text(encoding="utf-8"))
        for identifier in ids:
            if identifier in registry:
                continue
            where = f"「{target.title}」" if target is not None else "本文档"
            problems.append(
                Problem("POINTER", document.name, line, f"「{span}」 说 {identifier} 在{where}里，那里没有这个编号")
            )
    harvested = len(list(_POINTER.finditer(_mask_code(text))))
    if harvested != sum(boxes.values()):
        # The account has to add up against an *independent* count of the markers.
        # Recomputing the total from the boxes would reconcile by construction, which
        # is exactly how a box that stops incrementing (a ``continue`` moved one line
        # too early) survives as a clean run.
        problems.append(
            Problem(
                "RECONCILE",
                document.name,
                1,
                f"抽到 {harvested} 个「见」标记，分箱只落下 {sum(boxes.values())} 个：有一箱在计数前就跳过了",
            )
        )
    return problems, checked, boxes


def _appendix_section(token: str, headings: list[Section]) -> Section | None:
    normalized = token.replace(" ", "")
    for section in headings:
        if normalized in section.title.replace(" ", ""):
            return section
    return None


def check_links(document: Path, text: str) -> tuple[list[Problem], int, int]:
    """Resolve markdown links, separating ``missing`` from ``generated``.

    Returns ``(problems, checked, generated)``. A link is a claim about this
    repository, so three outcomes are possible and only one of them is red:

    * the target is tracked → satisfied;
    * the target is ignored by git (``output/playwright/*.png``) → the sentence is
      about an artifact a run produces, which a fresh clone cannot show and the
      repository was never going to hold. Counted, printed, not red — M8-T38
      opened on exactly these two links being red here and green there;
    * anything else → red, including the case ``exists on this disk but git has
      never seen it``, which is the dangling link that only the author can't see.

    A candidate outside the repository is judged by plain existence: outside the
    work tree there is no index to consult, and that is how a synthetic document
    in a temp directory still gets checked.

    Links written inside backticks or a fenced block are quotations, not claims — the
    same rule the pointer reader has honoured since M8-T37, and M8-T40 caught this
    reader without it: a batch record that *quoted* a link shape to explain itself was
    reported as a dangling link. The cost is the accepted one: a broken link that only
    ever appears inside code is invisible here too.
    """
    problems: list[Problem] = []
    checked = 0
    generated = 0
    for match in _LINK.finditer(_mask_code(text)):
        if not _link_judged(match):
            continue
        target = _link_target(match)
        checked += 1
        candidates = [(c, _inside_repo(c)) for c in (document.parent / target, REPO_ROOT / target)]
        inside = [(c, rel) for c, rel in candidates if rel is not None]
        if any(_holds(rel) for _, rel in inside):
            continue
        if any(_git_ignored(rel) for _, rel in inside):
            generated += 1
            continue
        if any(c.exists() for c, rel in candidates if rel is None):
            continue
        here = next((rel for c, rel in inside if c.exists()), None)
        detail = (
            f"链接目标 {target} 本机有（{here}），但 git 没有跟踪它，干净检出里这条链接是断的"
            if here
            else f"链接目标 {target} 不存在"
        )
        problems.append(Problem("LINK", document.name, _line_of(text, match.start()), detail))
    return problems, checked, generated


def check_document(document: Path) -> tuple[list[Problem], Stats]:
    text = document.read_text(encoding="utf-8")
    pointer_problems, pointers, boxes = check_pointers(document, text)
    link_problems, links, links_generated = check_links(document, text)
    evidence_problems, evidence = check_evidence(document, text)
    relative = document.relative_to(REPO_ROOT).as_posix()
    problems = pointer_problems + link_problems + evidence_problems
    minimum_pointers = MIN_POINTERS.get(relative)
    if minimum_pointers is not None and pointers < minimum_pointers:
        problems.append(
            Problem(
                "INVENTORY",
                relative,
                1,
                f"只 harvest 到 {pointers} 条可检查指针，低于下限 {minimum_pointers}：抽取器可能自己瞎了",
            )
        )
    minimum_links = MIN_LINKS.get(relative)
    if minimum_links is not None and links < minimum_links:
        problems.append(Problem("INVENTORY", relative, 1, f"只 harvest 到 {links} 条链接，低于下限 {minimum_links}"))
    minimum_evidence = MIN_EVIDENCE.get(relative)
    if minimum_evidence is not None and evidence < minimum_evidence:
        problems.append(
            Problem(
                "INVENTORY",
                relative,
                1,
                f"只 harvest 到 {evidence} 条文件/行号/测试名指针，低于下限 {minimum_evidence}：证据阅读器瞎了",
            )
        )
    prose = [claim for claim in prose_path_claims(text) if _is_path_claim(claim)]
    for claim in prose:
        rel = re.sub(r"^\./", "", claim)
        if _resolve_path(rel) is None and _exemption(rel) is None:
            problems.append(
                Problem(
                    "PROSE",
                    relative,
                    1,
                    f"散文里（反引号之外）写着路径 {claim}，仓库里没有，而且阅读器看不见它{_untracked_here(rel)}",
                )
            )
    return problems, Stats(
        pointers=pointers,
        markers=sum(boxes.values()),
        boxes=boxes,
        links=links,
        evidence=evidence,
        prose_paths=len(prose),
        links_generated=links_generated,
    )


# --------------------------------------------------------------------------- #
# Evidence pointers: files, line numbers and test names quoted in inline code.
#
# The reader above treats a code span as a *quotation* and skips it. This one
# lives inside code spans, because that is where the docs put their evidence:
# `minicc/webserver.py:324`, `tests/test_http_surface.py::test_x`. The two
# readers disagree on purpose — one man's citation is another man's claim.
# --------------------------------------------------------------------------- #

#: Roots a document-relative path may resolve against, beyond the repository root.
#: The docs abbreviate: ``agent/loop.py`` means ``minicc/agent/loop.py`` and
#: ``core/scope.js`` means ``web/src/core/scope.js``; a bare ``test_x.py::test_y``
#: needs ``tests``. Every entry below is measured to answer at least one shipped
#: citation, and a gate holds that — ``docs`` and ``scripts`` were dropped here
#: because a citation starting with either is already absolute from the repo root,
#: so those rows could never be reached (M8-T29's zero-reference constant, wearing
#: this file's own clothing).
_RESOLVE_ROOTS = ("", "minicc", "web/src", "tests")

#: Same list without the repo root: the heads a *relative* name may start with
#: and still be treated as a location claim. Derived from ``_RESOLVE_ROOTS`` so
#: admitting a claim and resolving it cannot drift into two separate decisions.
_ABBREVIATION_ROOTS = _RESOLVE_ROOTS[1:]

_CODE_SPAN = re.compile(r"`([^`\n]{1,140})`")
_FENCE = re.compile(r"```.*?```", re.S)
_TEST_REF = re.compile(r"^(?P<file>[\w./\-]+\.py)::(?P<test>test_[a-z0-9_]+)$")
_PATH_REF = re.compile(
    r"^(?P<path>[\w.\-/]+?\.(?:py|md|toml|json|txt|cfg|ini|sh|example|js|mjs|cjs|css|html))"
    r"(?::(?P<line>\d+))?(?:\.(?P<attr>\w+))?$"
)
_BARE_TEST = re.compile(r"^test_[a-z0-9_]+$")
_DIR_REF = re.compile(r"^(?P<path>[\w.\-]+(?:/[\w.\-]+)+)/?$")
_PROSE_PATH = re.compile(r"[\w.\-/]+\.(?:py|md|toml|json|txt|example)\b")
#: A code span that names a file with an optional line range: what a citation points
#: at when the evidence reader's "is this a path claim?" test says no (bare names, and
#: paths whose head is a directory git ignores).
_NAME_REF = re.compile(
    r"^(?P<path>[\w.\-/]+?\.\w{1,8})(?::(?P<lines>\d+(?:[,\-]\d+)*))?(?P<attr>\.\w+)?$"
)

#: Not files in this repository: the product reads or writes them at run time,
#: in the *user's* workspace. A reason is mandatory — a bare name in a set is
#: how an exemption quietly outlives the thing it excuses.
#:
#: M8-T38's ``exemption_usage`` reported five dead rows here, shipped by M8-T37
#: one batch after that batch wrote "a policy table row nobody reaches is a dead
#: row": a citation with no slash is never a location claim, so those five keys
#: could not be consulted. Deleted, not defended.
_NOT_A_REPO_PATH: dict[str, str] = {
    ".minicc/": "运行时在用户工作区读写的配置目录，不是本仓库的文件",
    "workspace/": "示例里用户的工作区路径",
    "out/": "示例输出目录",
    "src/": "被 agent 操作的用户项目文件示例",
}

#: Created by the build, absent from a clean checkout (M8-T4).
_BUILD_OUTPUT_PATH: dict[str, str] = {
    "minicc/web_static": "setup.py 的 build_py 在构建期把 web/ 复制进来",
    "minicc/ide_static": "同上，复制的是 ide/",
}

#: A deliverable an exit standard demands that still does not exist. Listed here
#: so the gap is a named row instead of a silently red gate — and so the day it
#: lands, this entry goes stale and the tool complains.
_PROMISED_PATH: dict[str, str] = {
    "docs/SECURITY_CHECKLIST.md": "M2 退出标准第 3 条要求的文件从未建立；攻击面目前只在 tests/test_security_perimeter.py 里",
    "tests/test_stream_merge.py": "M8-T11 验收要求新建的文件；逐字节合并断言实际落在 tests/test_m1_integrity.py",
    "benchmarks/fixture-workspaces/": "M4-T5 计划列了它，同文档的交付行明确写着**未单独建**——v2 fixture 用 "
    "tasks.v2.json 内联的 `fixture` 字典 + 独立 tempdir，磁盘种子树会和它漂移",
}

#: A path quoted *in order to say it is stale* — the sentence is about the
#: pointer, not an invitation to follow it.
_QUOTED_STALE_PATH: dict[str, str] = {
    "tests/test_core.py:1510": "roadmap 有一整段专门登记 M8-T6 拆分后的失效引用，引它正是为了说它已失效",
    "docs/PROJECT_REVIEW_2026-09-18.md:1413": "AUDIT 那段自己就写着「记录的规则已不存在」",
}

#: Removed on purpose. The document is not claiming the file is there; it is
#: recording a deletion, and in the enforced case a test keeps it deleted.
_RETIRED_PATH: dict[str, str] = {
    "web/app.min.js": "M4-T9 退役的压缩产物：`tests/test_cleanup_version.py::test_app_min_js_retired` 断言它不再存在、"
    "build-web.mjs 不再产出它。文档每一处引用都在描述这次删除",
    "web/src/01-core-state": "GAP 第十波记录的是当时的 9 个有序分片；`a97bf13` 把同一批代码重组为 "
    "`web/src/{core,chat,files,panels}` + main.js，编号分片因此消失",
}

#: A planning-stage name for something the delivery placed elsewhere. Not a
#: defect in the record — the record just has to say which branch was taken.
_DECLINED_PATH: dict[str, str] = {
    "minicc/agent/memory.py": "M8-T1 计划写的是「新增 `minicc/agent/memory.py`（或 `minicc/tools/memory.py`）」，"
    "交付选了后者；这个拼法从未存在",
}

#: Dated review snapshots: a line number in one of these was true on the date in
#: the filename, and rewriting it would falsify the record. Existence and test
#: names are still checked; ``:line`` is not.
_SNAPSHOT_DOCS: dict[str, str] = {
    "docs/AUDIT_2026-09-20.md": "带日期的复核快照，行号记录的是当天 HEAD 的位置",
    "docs/PROJECT_REVIEW_2026-09-18.md": "同上",
    "docs/OPTIMIZATION_DELIVERY_2026-09-18.md": "同上",
}

#: Documents about a different repository, where "exists in this repo" is the
#: wrong question.
_OUT_OF_SCOPE_DOCS: dict[str, str] = {
    "docs/SPECPROOF_ASSESSMENT.md": "通篇讲的是另一个仓库（SpecProof）的文件",
}

#: Floor per document: below it the extractor, not the docs, is the suspect.
#: Measured when M8-T37 landed: roadmap 576 claims, README 18 — the inventory grows
#: by a dozen every time a batch writes its own evidence, so quote a number only from
#: a live run. The floors sit far under those because
#: they guard the reader's eyesight, not the prose's length — and an *exempted*
#: citation still counts as considered, or a document whose pointers are mostly
#: exempt would report the same inventory as one with none.
MIN_EVIDENCE = {"docs/ROADMAP_TO_PRODUCT.md": 200, "README.md": 12}

_EVIDENCE_TABLES = (
    _NOT_A_REPO_PATH,
    _BUILD_OUTPUT_PATH,
    _PROMISED_PATH,
    _QUOTED_STALE_PATH,
    _RETIRED_PATH,
    _DECLINED_PATH,
)


@lru_cache(maxsize=None)
def _test_definitions(path: Path) -> dict[str, int]:
    """``{name: lineno}`` for every test function in a file, async included."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return {}
    return {
        node.name: node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test_")
    }


def _all_test_names() -> dict[str, str]:
    """Every test function name under tracked ``tests/*.py``, mapped to its file.

    An untracked test module is excluded for the same reason an untracked source
    file is: citing a test that only exists on this machine is a citation that
    resolves in neither a fresh clone nor CI.
    """
    found: dict[str, str] = {}
    for module in sorted((REPO_ROOT / "tests").glob("*.py")):
        if not _holds(f"tests/{module.name}"):
            continue
        for name in _test_definitions(module):
            found.setdefault(name, module.name)
    return found


def _resolve_path(rel: str) -> Path | None:
    """Resolve a citation against what the repository holds, not against this disk.

    No document-relative root: every claim that reaches here carries a slash (see
    ``_is_path_claim``), so a path written by a doc in ``docs/`` is still written
    from the repository root. The links reader is the one that resolves relative
    to the file, because markdown links really are relative.

    A file that exists here but is not tracked resolves to ``None`` on purpose:
    the citation would be dangling for everyone who clones this commit, and the
    red is emitted with ``_untracked_here`` saying which of the two it is.
    """
    for base in _RESOLVE_ROOTS:
        key = f"{base}/{rel}" if base else rel
        if _holds(key):
            return REPO_ROOT / key
    return None


def _exemption(span: str) -> str | None:
    """The reason this span is exempt, or ``None``. Empty reason is a bug, not a pass."""
    for table in _EVIDENCE_TABLES:
        for key, reason in table.items():
            assert reason.strip(), f"豁免 {key} 没有理由，等于没豁免"
            if span == key or (key.endswith("/") and span.startswith(key)):
                return reason
    return None


def _code_spans(text: str) -> list[tuple[int, str]]:
    fenced = _FENCE.sub(lambda m: " " * len(m.group(0)), text)
    return [(match.start(), match.group(1).strip()) for match in _CODE_SPAN.finditer(fenced)]


# --------------------------------------------------------------------------- #
# What the repository holds. Read from git, not from the working directory.
#
# Every set below is the answer to "would a fresh clone agree?" — which is the
# only question an exit standard can be checked against. ``iterdir()`` answers a
# different question: "what happened to be built here?"
# --------------------------------------------------------------------------- #


def _git_output(*args: str) -> list[str]:
    proc = subprocess.run(
        ("git", "-C", str(REPO_ROOT), *args), capture_output=True, text=True, encoding="utf-8"
    )
    if proc.returncode:
        return []
    return [line.replace("\\", "/").strip() for line in proc.stdout.splitlines() if line.strip()]


@lru_cache(maxsize=1)
def _tracked_files() -> frozenset[str]:
    """Every path git tracks, repo-relative, posix-separated."""
    return frozenset(_git_output("ls-files"))


@lru_cache(maxsize=1)
def _tracked_dirs() -> frozenset[str]:
    """Directories implied by tracked paths — git tracks files, not folders."""
    dirs: set[str] = set()
    for path in _tracked_files():
        parts = path.split("/")
        for cut in range(1, len(parts)):
            dirs.add("/".join(parts[:cut]))
    return frozenset(dirs)


@lru_cache(maxsize=1)
def _basenames() -> dict[str, tuple[str, ...]]:
    """Tracked paths grouped by file name — what a bare-name citation can land on."""
    grouped: dict[str, list[str]] = {}
    for path in _tracked_files():
        grouped.setdefault(path.rsplit("/", 1)[-1], []).append(path)
    return {name: tuple(sorted(paths)) for name, paths in grouped.items()}


def _holds(rel: str) -> bool:
    """Does the repository itself hold this path (file or implied directory)?"""
    return rel in _tracked_files() or rel in _tracked_dirs()


@lru_cache(maxsize=None)
def _git_ignored(rel: str) -> bool:
    """Would git refuse to track this path? That marks it as generated, not missing."""
    return subprocess.run(
        ("git", "-C", str(REPO_ROOT), "check-ignore", "-q", rel), capture_output=True
    ).returncode == 0


def _inside_repo(candidate: Path) -> str | None:
    """Repo-relative form of a resolved path, or ``None`` if it is outside."""
    try:
        return candidate.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return None


def _untracked_here(rel: str) -> str:
    """Suffix for a red that only makes sense on this machine: the file exists, git has it not."""
    for base in _RESOLVE_ROOTS:
        key = f"{base}/{rel}" if base else rel
        if (REPO_ROOT / key).exists():
            return f"（本机有 {key}，但 git 没有跟踪它，所以干净检出里这条引用是悬空的）"
    return ""


@lru_cache(maxsize=1)
def _top_level() -> frozenset[str]:
    """Top-level directories the repository holds — from git, never from ``iterdir``.

    M8-T37 measured the same HEAD reporting 811 evidence pointers on the machine
    that had been building and running things here, and 782 in a clean checkout.
    Nothing in the documents differed: this set came from the working directory,
    so ``output/``, ``.minicc/`` and ``.venv/`` — which exist only because
    something ran here — silently turned non-claims into claims. A tool whose
    inventory depends on which machine cloned the repository cannot back an exit
    standard, so the claim set is now a function of what git tracks.
    """
    return frozenset(path.split("/", 1)[0] for path in _tracked_files() if "/" in path)


@lru_cache(maxsize=1)
def _abbreviation_heads() -> frozenset[str]:
    """Directory names a package-relative citation may start with.

    Derived from the same ``_ABBREVIATION_ROOTS`` the resolver tries, so a head
    cannot be admitted as a claim by one function and then fail to resolve
    because the other list forgot it. Tracked content only, for the same reason
    ``_top_level`` is.
    """
    heads: set[str] = set()
    for base in _ABBREVIATION_ROOTS:
        prefix = base + "/"
        for path in _tracked_files():
            rest = path[len(prefix) :] if path.startswith(prefix) else ""
            if "/" in rest:
                heads.add(rest.split("/", 1)[0])
    return frozenset(heads)


def _is_path_claim(span: str) -> bool:
    """Is this code span a claim about a *path*, or just a name?

    A bare ``loop.py`` is shorthand for a module the reader is expected to find,
    and the docs use it dozens of times; only ``head/rest`` forms are citations
    with a location to check. The head must be a real top-level directory, a
    registered exemption, or a directory under one of the abbreviation roots —
    ``agent/loop.py`` means ``minicc/agent/loop.py`` and ``core/scope.js`` means
    ``web/src/core/scope.js``, which is how the docs actually cite them. That
    last branch accepts only a span carrying a file extension, because
    ``tools/call`` is an RPC method name and ``llm/stream_merge`` a module, not
    locations. Requiring a known head is what keeps ``127.0.0.0/8`` and
    ``--session-id/--resume`` out of the claim set.
    """
    if " " in span or "://" in span:
        return False
    head, _, rest = span.partition("/")
    if not rest:
        return False
    if head.startswith("-"):
        return False
    exempt = any(span.startswith(key) for table in _EVIDENCE_TABLES for key in table)
    if head in _top_level() or exempt:
        return True
    return _PATH_REF.match(span) is not None and head in _abbreviation_heads()


def _evidence_shape(span: str) -> str | None:
    """Which kind of evidence claim a code span is, or None if it is just a name.

    Split out of ``check_evidence`` so the inventory counts *what the reader
    considered*, exemptions included: if exempted spans were skipped before the
    counter, a document whose citations are mostly exempt would look like a
    document with no citations, and the floor would report a blind reader.
    """
    if _TEST_REF.match(span) or _BARE_TEST.match(span):
        return "test"
    if _PATH_REF.match(span) or _DIR_REF.match(span):
        return "path" if _is_path_claim(span) else None
    return None


def check_evidence(document: Path, text: str) -> tuple[list[Problem], int]:
    """Verify every file / line / attribute / test-name claim inside inline code."""
    relative = document.relative_to(REPO_ROOT).as_posix() if document.is_relative_to(REPO_ROOT) else document.name
    if relative in _OUT_OF_SCOPE_DOCS:
        return [], 0
    problems: list[Problem] = []
    names = _all_test_names()
    stems = {module.stem for module in (REPO_ROOT / "tests").glob("*.py") if _holds(f"tests/{module.name}")}
    checked = 0
    for offset, span in _code_spans(text):
        line = _line_of(text, offset)
        if _evidence_shape(span) is None:
            continue
        checked += 1
        # An exemption is registered against the *citation as written*, so it has
        # to be consulted before any of the sub-checks. Reading it only in the
        # "file does not exist" branch let a stale `path:line` citation still fire
        # a past-EOF complaint against a file that does exist.
        if _exemption(span) is not None:
            continue
        ref = _TEST_REF.match(span)
        if ref:
            target = _resolve_path(ref.group("file"))
            if target is None:
                if _exemption(ref.group("file")) is None:
                    problems.append(
                        Problem("EVIDENCE", document.name, line, f"{span} 指向的文件不存在{_untracked_here(ref.group('file'))}")
                    )
                continue
            if ref.group("test") not in _test_definitions(target):
                hint = difflib.get_close_matches(ref.group("test"), names, n=1, cutoff=0.78)
                where = f"它定义在 {hint[0]}" if hint else "整个 tests/ 里没有这个函数"
                problems.append(Problem("EVIDENCE", document.name, line, f"{span} 没有这个测试：{where}"))
            continue
        if _BARE_TEST.match(span):
            if span in names or span in stems:
                continue
            hint = difflib.get_close_matches(span, list(names), n=1, cutoff=0.78)
            problems.append(
                Problem(
                    "EVIDENCE",
                    document.name,
                    line,
                    f"{span} 既不是测试文件名也不是任何测试函数名" + (f"，最接近的是 {hint[0]}" if hint else ""),
                )
            )
            continue
        path_ref = _PATH_REF.match(span)
        rel = (path_ref or _DIR_REF.match(span)).group("path")
        target = _resolve_path(rel)
        if target is None:
            if _exemption(rel) is None:
                problems.append(
                    Problem("EVIDENCE", document.name, line, f"{span} 指向的路径在仓库里不存在{_untracked_here(rel)}")
                )
            continue
        if path_ref is None:
            continue
        if path_ref.group("line") and relative not in _SNAPSHOT_DOCS:
            count = len(target.read_text(encoding="utf-8", errors="replace").splitlines())
            wanted = int(path_ref.group("line"))
            if wanted > count:
                problems.append(Problem("EVIDENCE", document.name, line, f"{span} 在第 {count} 行之外（文件只有 {count} 行）"))
        attribute = path_ref.group("attr")
        if attribute and attribute not in target.read_text(encoding="utf-8", errors="replace"):
            problems.append(Problem("EVIDENCE", document.name, line, f"{span} 说 {rel} 里有 {attribute}，那里没有"))
    return problems, checked


def prose_path_claims(text: str) -> list[str]:
    """Path-shaped tokens **outside** code spans — what the reader above cannot see.

    The evidence reader only looks inside backticks, so if the docs start citing
    paths in prose a floor alone would not notice. Bare file names do not count
    (``loop.py`` in prose is a shorthand, not a path claim); a slash does.
    """
    return [m.group(0) for m in _PROSE_PATH.finditer(_mask_code(text)) if "/" in m.group(0)]


def exemption_usage(documents: list[Path]) -> dict[str, int]:
    """How many shipped citations each exemption key actually answered.

    An exemption nobody reaches is the same defect M8-T29 found in a constant and
    M8-T37 found in a resolve root: a table that looks like policy. This one is
    easy to grow stale, because a rule change elsewhere in the reader — say,
    heads that no longer come from ``iterdir()`` — can silently make a key
    unreachable while its reason and its document reference both stay intact.
    """
    hits: dict[str, int] = {key: 0 for table in _EVIDENCE_TABLES for key in table}
    for document in documents:
        if not document.exists():
            continue
        relative = document.relative_to(REPO_ROOT).as_posix() if document.is_relative_to(REPO_ROOT) else ""
        if relative in _OUT_OF_SCOPE_DOCS:
            continue
        text = document.read_text(encoding="utf-8")
        spans = [span for _, span in _code_spans(text)]
        spans += [claim for claim in prose_path_claims(text) if _is_path_claim(claim)]
        for span in spans:
            if _evidence_shape(span) is None:
                continue
            reason = _exemption(span)
            if reason is None:
                continue
            for key in hits:
                if key == span or (key.endswith("/") and span.startswith(key)):
                    hits[key] += 1
    return hits


def check_exempt_tables(documents: list[Path]) -> list[Problem]:
    """Every exemption must still be earning its place in at least one document."""
    haystack = "\n".join(path.read_text(encoding="utf-8") for path in documents if path.exists())
    problems: list[Problem] = []
    for table in _EVIDENCE_TABLES:
        for key, reason in table.items():
            if not reason.strip():
                problems.append(Problem("EXEMPT", "doc_pointers.py", 1, f"豁免 {key} 没有理由"))
            if key not in haystack:
                problems.append(Problem("EXEMPT", "doc_pointers.py", 1, f"豁免 {key} 已无任何文档引用，是陈旧登记"))
    for doc, reason in _SNAPSHOT_DOCS.items():
        if not reason.strip():
            problems.append(Problem("EXEMPT", "doc_pointers.py", 1, f"快照文档豁免 {doc} 没有理由"))
        elif not (REPO_ROOT / doc).exists():
            problems.append(Problem("EXEMPT", "doc_pointers.py", 1, f"快照文档 {doc} 已不存在，豁免是空的"))
    if problems:
        # An empty reason makes ``_exemption`` raise on purpose, so hit counting
        # cannot run against a malformed table. The shape complaint is the
        # dominant one; liveness is measured only by a working instrument.
        return problems
    for key, hits in exemption_usage(documents).items():
        if hits == 0:
            problems.append(
                Problem("EXEMPT", "doc_pointers.py", 1, f"豁免 {key} 没有命中任何在仓引用：这条规则现在挡不到东西，是死行")
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("documents", nargs="*", type=Path, default=DEFAULT_DOCS)
    parser.add_argument("--check", action="store_true", help="exit non-zero on any dangling reference")
    parser.add_argument("--quiet", action="store_true", help="print only problems and the totals")
    args = parser.parse_args(argv)

    problems: list[Problem] = []
    totals = {"pointers": 0, "markers": 0, "links": 0, "evidence": 0, "prose_paths": 0, "links_generated": 0}
    account = {box: 0 for box in POINTER_BOXES}
    for document in args.documents:
        if not document.exists():
            problems.append(Problem("MISSING", document.name, 1, "文档不存在"))
            continue
        found, stats = check_document(document)
        problems.extend(found)
        for key in totals:
            totals[key] += getattr(stats, key)
        for box, count in stats.boxes.items():
            account[box] = account.get(box, 0) + count
        if not args.quiet:
            boxes = " ".join(f"{box}={stats.boxes.get(box, 0)}" for box in POINTER_BOXES)
            print(
                f"{document.name}: markers={stats.markers} {boxes} "
                f"links={stats.links} evidence={stats.evidence} prose-paths={stats.prose_paths}"
            )
    unknown = sorted(set(account) - set(POINTER_BOXES))
    if unknown:
        # A box that exists but is never printed is an account with a page torn out.
        problems.append(
            Problem("INVENTORY", "doc_pointers.py", 1, f"分箱出现了没登记的名字：{'、'.join(unknown)}")
        )
    if not _tracked_files():
        problems.append(
            Problem(
                "INVENTORY",
                "doc_pointers.py",
                1,
                "git ls-files 一条都没返回：这个目录不是仓库，或 git 不可用，于是「在仓库里存在」全部判否",
            )
        )
    problems.extend(check_exempt_tables(list(args.documents)))
    for problem in problems:
        print(f"DANGLING {problem}")
    tally = " ".join(f"{box}={account[box]}" for box in POINTER_BOXES)
    print(
        f"checked {totals['pointers']} of {totals['markers']} 「见」 markers ({tally}), "
        f"{totals['links']} links ({totals['links_generated']} of them into git-ignored generated output) "
        f"and {totals['evidence']} evidence pointers ({totals['prose_paths']} path claims sit outside code spans) "
        f"in {len(args.documents)} documents, over {len(_tracked_files())} tracked files"
    )
    return 1 if (problems and args.check) else 0


if __name__ == "__main__":
    raise SystemExit(main())
