"""M8-T562 — the wide face keeps every file it ran and every reader of the docs.

The 542 wide face had to be re-derived from a fixed baseline because the 541
roster had been swept away.  This gate freezes that run set in
``tests/fence_rosters/wide.txt`` and makes two promises standing:

* every name in the frozen set is still a tracked test module — a file leaves
  the wide face only through a conscious edit of the roster, which the batch
  record then has to name;
* every test module that *structurally* reads the document population (a
  ``glob``/``rglob`` of a ``*.md`` literal, or a read of ``DEFAULT_DOCS``) is
  inside the frozen set — a new document-reading gate has to widen the wide
  face in the same batch that lands it.

Admission is structural, not lexical: the 542 gate pins the ``DEFAULT_DOCS``
assignment and ``glob("*.md")`` as text inside string constants, and a byte
needle would charge it as a reader.  It reads no document, and the last leg
keeps that distinction alive on synthetic sources.

Boundary: the predicate hears a constant pattern only.  ``glob(pattern)`` with
a variable is not guessed at; a reader that builds its pattern at runtime is
outside the census, and the roster is where it gets admitted by hand.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROSTER = REPO / "tests" / "fence_rosters" / "wide.txt"

#: The roster as landed: the 542 wide run set.  It may only grow by a
#: conscious edit; the floor keeps a truncated file from passing as complete.
WIDE_FLOOR = 479

#: Readers found on the bytes that landed the gate.  A floor, not a ledger:
#: the walk below names any reader missing from the roster.
READER_FLOOR = 9

#: One witness per admission reason, so a predicate that goes blind reds here
#: before the census quietly empties.
WITNESSES = {
    "tests/test_doc_pointers.py": ["DEFAULT_DOCS"],
    "tests/test_no_document_quotes_a_content_addressed_bundle.py": ['rglob("*.md")'],
}

#: A gate whose pin only *mentions* the reader shapes as strings, reading no
#: document.  It belongs to the roster but must stay out of the reader census.
MENTION_ONLY = "tests/test_a_roadmap_cite_of_the_pointer_checker_can_be_read.py"


def _tracked() -> list[str]:
    proc = subprocess.run(
        ["git", "-C", str(REPO), "ls-files"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return proc.stdout.splitlines()


def _is_test_module(name: str) -> bool:
    return name.startswith("tests/") and name.endswith(".py")


def _tracked_tests() -> list[str]:
    return [name for name in _tracked() if _is_test_module(name)]


def doc_reader_reasons(source: str) -> list[str]:
    """The shapes by which this source reads the document population."""
    reasons: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) and node.attr == "DEFAULT_DOCS":
            reasons.add("DEFAULT_DOCS")
        elif isinstance(node, ast.Name) and node.id == "DEFAULT_DOCS":
            reasons.add("DEFAULT_DOCS")
        elif isinstance(node, ast.Call) and node.args:
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
            first = node.args[0]
            if (
                name in {"glob", "rglob"}
                and isinstance(first, ast.Constant)
                and isinstance(first.value, str)
                and "*" in first.value
                and first.value.endswith(".md")
            ):
                reasons.add(f'{name}("{first.value}")')
    return sorted(reasons)


def _read(name: str) -> str:
    return (REPO / name).read_text(encoding="utf-8", errors="replace")


def test_every_file_of_the_wide_baseline_is_still_a_tracked_test() -> None:
    # Universal newlines: the blob is LF, but autocrlf=true checks it out as
    # CRLF, and the roster must read the same on either plane.
    baseline = ROSTER.read_text(encoding="utf-8").splitlines()
    tracked = _tracked()
    assert ROSTER.relative_to(REPO).as_posix() in tracked, (
        "名册自己没有被跟踪：它只能是交付物，不能是本地便条"
    )
    assert baseline == sorted(baseline), "名册必须排序，排序后的行才能逐名对账"
    assert len(baseline) == len(set(baseline)), "名册里有重复行"
    bad = [name for name in baseline if not _is_test_module(name)]
    assert bad == [], f"名册里出现不是测试模块的名字：{bad[:10]}"
    assert len(baseline) >= WIDE_FLOOR, (
        f"名册只剩 {len(baseline)} 行，低于落地时的 {WIDE_FLOOR}：是被截断还是被顺手清掉了？"
    )
    dropped = sorted(set(baseline) - set(tracked))
    assert dropped == [], (
        f"这些文件在 542 的宽面里跑过，今天不再是被跟踪的测试：{dropped}。"
        f"宽面只许变宽；确实要删的，先改这里并在记录里点名"
    )


def test_every_document_reader_is_inside_the_wide_baseline() -> None:
    baseline = set(ROSTER.read_text(encoding="utf-8").splitlines())
    tracked = _tracked_tests()
    reasons: dict[str, list[str]] = {}
    for name in tracked:
        got = doc_reader_reasons(_read(name))
        if got:
            reasons[name] = got

    for name, expected in WITNESSES.items():
        assert name in tracked, f"见证文件 {name} 不在被跟踪的测试里"
        assert reasons.get(name) == expected, (
            f"见证文件 {name} 的读法由 {expected} 变成了 {reasons.get(name)}："
            f"AST 谓词瞎了，还是这份文件不再读文档？（换见证要连同谓词一起改）"
        )
    assert len(reasons) >= READER_FLOOR, (
        f"只找到 {len(reasons)} 份文档读者，低于落地时的 {READER_FLOOR}：普查瞎了"
    )

    missing = sorted(set(reasons) - baseline)
    assert missing == [], (
        "这些测试在读文档，却不在宽面名册里（新读者要在同一批里被收进宽面）：\n"
        + "\n".join(f"  {name} -> {reasons[name]}" for name in missing)
    )


def test_a_mention_of_a_reader_is_not_a_reader() -> None:
    samples = (
        ('PIN = \'DEFAULT_DOCS = tuple(sorted((REPO / "docs").glob("*.md")))\'\n', [],
         "字符串常量里提到的读法不是读法"),
        ("for path in dp.DEFAULT_DOCS:\n    pass\n", ["DEFAULT_DOCS"], "属性读法"),
        ("for path in DEFAULT_DOCS:\n    pass\n", ["DEFAULT_DOCS"], "直接导入的名字也是读法"),
        ('for path in DOCS.rglob("*.md"):\n    pass\n', ['rglob("*.md")'], "rglob 读法"),
        ('for path in ROOT.glob("*.py"):\n    pass\n', [], "glob 的不是文档"),
        ("for path in ROOT.glob(pattern):\n    pass\n", [], "非常量模式不猜"),
        ('for path in ROOT.glob("*.md.txt"):\n    pass\n', [], "后缀不是 .md"),
    )
    for source, expected, why in samples:
        assert doc_reader_reasons(source) == expected, (
            f"{why}：{source!r} -> {doc_reader_reasons(source)}，应为 {expected}"
        )

    shipped = _read(MENTION_ONLY)
    assert 'glob("*.md")' in shipped, (
        f"{MENTION_ONLY} 里已经没有那个字面量，这条控制失去了载体"
    )
    assert doc_reader_reasons(shipped) == [], (
        f"{MENTION_ONLY} 只在字符串里提到读法，却被 census 当成读者：{doc_reader_reasons(shipped)}"
    )
    assert MENTION_ONLY in ROSTER.read_text(encoding="utf-8").splitlines(), (
        "只提不读的判据也在宽面里：排除的是读者身份，不是文件"
    )
