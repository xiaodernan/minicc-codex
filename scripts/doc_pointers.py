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
    is what makes the extraction precise. Skipped spans are counted and printed
    as ``unresolved``, because "this pointer names no locator" is a real gap in
    what the tool guards — e.g. ``口径见下方注记`` cannot be checked at all.
    A locator must resolve to a heading, and any id in the same pointer must be
    **declared** inside that locator's section — as a heading or as a table row's
    label cell, not merely mentioned. Mentioning cannot work: 「见下方「第十八批
    M8-T34」」 itself spells the id out, so "does the id appear in the section?"
    would be answered yes by the pointer. Naming both a section and an id is a
    claim about where that id is *recorded*, and that is the claim M8-T34 got
    wrong.

``link``
    ``[text](target)`` with a non-URL target must resolve on disk, relative to
    the document's directory or the repository root.

Counts for both are printed, and ``--check`` fails when the inventory is
suspiciously small too: an empty harvest means the extractor went blind, which
is the same failure mode as a coverage denominator that quietly shrinks
(M8-T35's 34 → 31 incident).
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
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
_SECTION = re.compile(r"第([一二三四五六七八九十]+)节")
_BATCH = re.compile(r"第([一二三四五六七八九十]+)批(续二|续)?")
_APPENDIX = re.compile(r"附录\s*([A-Z])")
_ID = re.compile(r"\b([MP]\d+(?:-[A-Z]?\d+|\.\d+)?)\b")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.M)
_ROW = re.compile(r"^\|(.+)$", re.M)
_LINK = re.compile(r"\[([^\]\n]{1,120})\]\(([^)\s]{1,160})\)")
_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


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
    unresolved: int
    links: int


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


def _cn_numeral(word: str) -> int | None:
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
    """Map ``N`` to the level-2 heading whose title starts ``N、``.

    The roadmap writes ``## 四、明确不做什么`` while prose says 「第四节」, so the
    two spellings have to be tied together before a section pointer means
    anything.
    """
    out: dict[int, Section] = {}
    for section in headings:
        if section.level != 2:
            continue
        match = re.match(r"^([一二三四五六七八九十]+)、", section.title)
        if match:
            numeral = _cn_numeral(match.group(1))
            if numeral is not None:
                out[numeral] = section
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


def _pointer_spans(text: str) -> list[tuple[int, str]]:
    """(offset, span) for every ``见`` marker, quote-delimited forms first."""
    out: list[tuple[int, str]] = []
    for match in _POINTER.finditer(_mask_code(text)):
        quoted = match.group(2)
        if quoted is not None:
            out.append((match.start(), quoted.strip()))
            continue
        direction = match.group(3) or ""
        out.append((match.start(), f"{direction}{match.group(4) or ''}".strip()))
    return out


def check_pointers(document: Path, text: str) -> tuple[list[Problem], int, int]:
    """Return problems, the number of checked pointers, and unresolved spans."""
    headings = sections(text)
    numbered = _numbered_headings(headings)
    batch_labels = _batch_labels(headings)
    problems: list[Problem] = []
    checked = 0
    unresolved = 0
    for offset, span in _pointer_spans(text):
        batches = list(_BATCH.finditer(span))
        secs = list(_SECTION.finditer(span))
        appendices = list(_APPENDIX.finditer(span))
        ids = _ID.findall(span)
        if not (batches or secs or appendices or ids):
            unresolved += 1  # a marker naming no locator: a gap in what is guarded
            continue
        checked += 1
        line = _line_of(text, offset)
        target: Section | None = None
        remote: list[Section] = []
        for sec in secs:
            numeral = _cn_numeral(sec.group(1))
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
    return problems, checked, unresolved


def _appendix_section(token: str, headings: list[Section]) -> Section | None:
    normalized = token.replace(" ", "")
    for section in headings:
        if normalized in section.title.replace(" ", ""):
            return section
    return None


def check_links(document: Path, text: str) -> tuple[list[Problem], int]:
    problems: list[Problem] = []
    checked = 0
    for match in _LINK.finditer(text):
        target = match.group(2).split("#")[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        checked += 1
        if (document.parent / target).exists() or (REPO_ROOT / target).exists():
            continue
        problems.append(
            Problem("LINK", document.name, _line_of(text, match.start()), f"链接目标 {target} 不存在")
        )
    return problems, checked


def check_document(document: Path) -> tuple[list[Problem], Stats]:
    text = document.read_text(encoding="utf-8")
    pointer_problems, pointers, unresolved = check_pointers(document, text)
    link_problems, links = check_links(document, text)
    relative = document.relative_to(REPO_ROOT).as_posix()
    problems = pointer_problems + link_problems
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
    return problems, Stats(pointers=pointers, unresolved=unresolved, links=links)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("documents", nargs="*", type=Path, default=DEFAULT_DOCS)
    parser.add_argument("--check", action="store_true", help="exit non-zero on any dangling reference")
    parser.add_argument("--quiet", action="store_true", help="print only problems and the totals")
    args = parser.parse_args(argv)

    problems: list[Problem] = []
    totals = {"pointers": 0, "unresolved": 0, "links": 0}
    for document in args.documents:
        if not document.exists():
            problems.append(Problem("MISSING", document.name, 1, "文档不存在"))
            continue
        found, stats = check_document(document)
        problems.extend(found)
        for key in totals:
            totals[key] += getattr(stats, key)
        if not args.quiet:
            print(f"{document.name}: pointers={stats.pointers} unresolved={stats.unresolved} links={stats.links}")
    for problem in problems:
        print(f"DANGLING {problem}")
    print(
        f"checked {totals['pointers']} pointers ({totals['unresolved']} spans name no locator) "
        f"and {totals['links']} links in {len(args.documents)} documents"
    )
    return 1 if (problems and args.check) else 0


if __name__ == "__main__":
    raise SystemExit(main())
