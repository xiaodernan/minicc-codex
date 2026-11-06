"""M8-T561 — a line the record cites of the pointer checker can be re-read.

The record names ``scripts/doc_pointers.py`` by line number in a handful of
clusters.  The checker's own pointer gate asks only whether a number is inside
the file (``_line_of``), so a splice that shifts lines leaves every citation
in range while the line the sentence was written for has moved on.

This gate pins the *text* of each cited line, not its number.  A splice reds
the first leg; the repair is to re-aim the citation and this table.  The
second leg is the parser's control: it must hear the shape a per-line scan
misses (a citation split across a line break) and must not charge the shapes
that share a line with the checker's name (another file's citation, a clock
string, a sentence that already ended, a prose colon before a count).

The measured counts live in the batch record, not here: this file only says
what each cited line has to keep containing.

Boundary: a cite belongs to the checker only inside the cluster its filename
opens — from the name forward until a sentence end, a blank line, or another
filename.  Three bare ``:1557``-era cites sit in *other* sentences as records
of a historical population; they are deliberately outside this gate, because
re-aiming a measurement to a reordered line would state something the prose
never measured.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROADMAP = REPO / "docs" / "ROADMAP_TO_PRODUCT.md"
TARGET = "scripts/doc_pointers.py"

FILENAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:py|md|mjs|js|ts|tsx|json|ya?ml)")

#: The checker's own vocabulary is the ASCII colon (``_NAME_REF``); a full-width
#: colon followed by a count is prose, not a citation.
CITE = re.compile(r":(\d{2,4})(?![0-9])")

STOPS = "。；！？"

#: line -> the thing the citing sentence says is there.  A pin is the line's
#: stripped text, so indentation may change and a reflow may not.
PINS = {
    64: 'DEFAULT_DOCS = tuple(sorted((REPO_ROOT / "docs").glob("*.md"))) + (REPO_ROOT / "README.md",)',
    138: '_NUM = r"(\\d+|[一二三四五六七八九十]+)"',
    266: "def _line_of(starts: tuple[int, ...], offset: int) -> int:",
    514: "run, info = match.group(1), match.group(2)",
    654: '"""``carried-by-link-reader`` is a promise that another reader answers for this',
    846: "if _git_ignored(path):",
    884: "for offset, span, box, targets in _pointer_spans(text):",
    1010: "for offset in _fence_blocks(text)[1]:",
    1076: "for match in _LINK.finditer(_mask_code(text)):",
    1585: "for offset, span in _code_spans(text):",
    1588: "line = _line_of(starts, offset)",
}

#: The corpus at the time the gate landed: nine clusters, 19 citations.  The
#: floor only guards against a parser that silently sees fewer; the record's
#: own citations may raise it.
MIN_CITES = 19


def _cluster_end(text: str, start: int) -> int:
    """Where the citation cluster opened at ``start`` ends.

    A sentence end, a blank line, or another file's name closes it: a cite of
    ``roadmap`` or of ``tests/test_core.py`` on the same line is not a cite of
    the checker, and a clock string after it is not a cite at all.
    """
    end = len(text)
    for i in range(start, len(text)):
        if text[i] in STOPS:
            end = i
            break
        if text[i] == "\n":
            j = i + 1
            while j < len(text) and text[j] in " \t\r":
                j += 1
            if j < len(text) and text[j] == "\n":
                end = i
                break
    nxt = FILENAME.search(text, start)
    if nxt and nxt.start() < end:
        end = nxt.start()
    return end


def clusters(text: str) -> list[tuple[int, int, list[int]]]:
    """``(start, end, numbers)`` for each place the checker's name opens a cite."""
    found: list[tuple[int, int, list[int]]] = []
    for match in FILENAME.finditer(text):
        if match.group(0) != TARGET:
            continue
        end = _cluster_end(text, match.end())
        numbers: list[int] = []
        for cite in CITE.finditer(text, match.end(), end):
            if cite.start() and text[cite.start() - 1].isdigit():
                continue  # 0:18:36 is a duration, not a line
            numbers.append(int(cite.group(1)))
        found.append((match.start(), end, numbers))
    return found


def cited_numbers(text: str) -> list[int]:
    return [number for _, _, numbers in clusters(text) for number in numbers]


def test_every_cite_of_the_checker_names_the_line_it_is_pinned_to() -> None:
    text = ROADMAP.read_text(encoding="utf-8", errors="replace")
    lines = (REPO / TARGET).read_text(encoding="utf-8", errors="replace").splitlines()
    found = cited_numbers(text)

    # The set comparison comes first: it names which cite is unaccounted for.
    # The floor is the second guard, for a parser that still sees every distinct
    # number but loses duplicate instances (the A10 arm) -- put first, it would
    # report a lost number as merely "too few cites" and hide the specific one.
    missing = sorted(set(PINS) - set(found))
    extra = sorted(set(found) - set(PINS))
    assert not missing and not extra, (
        f"记录里该引却没引的钉子 {missing}；记录里引了却没人钉的号 {extra}。"
        f"前者说明 splice 之后该重瞄的那一行丢了，后者说明新写的行号还没进 PINS"
    )
    assert len(found) >= MIN_CITES, (
        f"记录里点名 {TARGET} 的引用只解析到 {len(found)} 条，低于落地时的 {MIN_CITES} 条："
        f"解析器瞎了，还是那几段记录被删了？{found}"
    )
    absent = []
    for number, token in sorted(PINS.items()):
        assert 1 <= number <= len(lines), f"钉子 :{number} 越界：文件只有 {len(lines)} 行"
        line = lines[number - 1].strip()
        if token not in line:
            absent.append((number, token, line))
    assert absent == [], "钉子不在它守着的那一行上（splice 之后要重瞄并改钉）：\n" + "\n".join(
        f"  :{number} 应含 {token!r}，实际是 {line!r}" for number, token, line in absent
    )


def test_the_parser_hears_the_shapes_a_per_line_scan_misses() -> None:
    samples = (
        ("`scripts/doc_pointers.py` 的 `:863`、`:989`", [863, 989], "同一行"),
        ("`scripts/doc_pointers.py` 的四个循环（`:863`、`:989`、\n`:1054`、`:1556`）",
         [863, 989, 1054, 1556], "跨行：按行扫只看得见前两个"),
        ("`scripts/doc_pointers.py:641`", [641], "显式形式"),
        ("`scripts/doc_pointers.py` 的 :256-257", [256], "范围引用只认首行"),
        ("`scripts/doc_pointers.py --check` 跑了 (0:18:36)", [], "时钟不是行号"),
        ("`scripts/doc_pointers.py` exit 0。后面 roadmap `:939`", [], "句号已经关掉了这一段"),
        ("`tests/test_doc_pointers.py:270`", [], "同名 basename 的另一个文件"),
        ("`scripts/doc_pointers.py` 的 `:868` 与 `tests/test_core.py:1510`", [868],
         "同一句里别人的引用不记在它头上"),
        ("`scripts/doc_pointers.py` --check 后同一份：257 passed", [], "全角冒号接计数是散文"),
    )
    for text, expected, why in samples:
        assert cited_numbers(text) == expected, f"{why}：{text!r} -> {cited_numbers(text)}，应为 {expected}"


def test_a_cite_of_another_file_with_the_same_basename_is_not_charged() -> None:
    """A parser that keys on ``doc_pointers.py`` as a suffix would charge these."""
    text = (
        "`tests/test_doc_pointers.py:270` 与 `tests/test_doc_pointers.py:391`\n"
        "以及 `scripts/doc_pointers.py:868`\n"
    )
    assert cited_numbers(text) == [868], cited_numbers(text)
