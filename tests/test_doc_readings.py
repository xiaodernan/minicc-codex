"""M8-T87: a reading a document pins as reproducible has to be reproducible now.

``docs/BENCHMARK_EVALUATION.md`` closes its focused-run section with a pinned reading and
an instruction to refill it from a fresh run:

    .venv/Scripts/python.exe -m pytest tests/test_benchmark_runner.py tests/test_behavior_bench.py -q -o addopts=''
    2026-09-29 复现结果：上面「评测器定向检查」命令逐字输出 `31 passed in 19.74s`（…如需更新请重跑该命令并原样回填）

That line read ``27 passed in 9.48s`` until this batch, while the command above it printed
``31 passed in 19.74s`` on the same tree: four cases had been added to those two files and
the number never moved.  The audit file had already recorded the same rot once
(``docs/AUDIT_2026-09-20.md``: the line stood at 23 while the tree printed 27), so this is
a class, not an incident - the document is the project's record of reproducible evidence,
and a number nobody re-derives stops being evidence.

The document also says what the number tracks - "数字随这两套测试的用例数变化" - so this gate
re-derives the case count by collecting exactly the files the recorded command names.  The
elapsed time in the same sentence is deliberately not checked: a wall clock moves with the
machine, and the line only claims it is what the command printed.  The sentence shape is
checked, though, because the pin is supposed to be the verbatim tail of a pytest run.

No line numbers are pinned anywhere here: the reading is found by the file names its own
command carries, which is the locator the document itself provides.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: (document, the test files its recorded command names).  A pin is a promise that the
#: document is re-runnable *as written*, so only a reading whose own text says it is a
#: reproduction result belongs here - the per-batch numbers in
#: ``docs/ROADMAP_TO_PRODUCT.md`` record a tree at a commit and are not pins.
PINS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("docs/BENCHMARK_EVALUATION.md",
     ("tests/test_benchmark_runner.py", "tests/test_behavior_bench.py")),
)

_BLOCK = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.S)
_READING = re.compile(r"(\d+)\s*passed in\s*[\d.]+s")
_COLLECTED = re.compile(r"(\d+)\s+tests?\s+collected")
_LOOKAHEAD = 600


def recorded_reading(doc: Path, files: tuple[str, ...]) -> tuple[str, int] | None:
    """The recorded command plus the case count pinned after it, or ``None``.

    ``None`` means the document no longer carries a reading under a command that names
    ``files``.  The callers below treat that as a failure rather than as "nothing to
    check": a pin that cannot find its own sentence guards nothing.
    """
    text = doc.read_text(encoding="utf-8")
    for block in _BLOCK.finditer(text):
        command = block.group(1).strip()
        if "pytest" not in command or not all(name in command for name in files):
            continue
        hit = _READING.search(text[block.end():block.end() + _LOOKAHEAD])
        return (command, int(hit.group(1))) if hit else None
    return None


def collected_count(files: tuple[str, ...]) -> tuple[int, str]:
    """How many cases this tree collects for ``files``; ``-1`` when it collected nothing."""
    probe = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-o", "addopts=",
         "-p", "no:cacheprovider", *files],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300,
        # A parent decoder pinned alone turns a crash into mojibake: the child
        # has to be told the same codec, or its report arrives in the machine
        # code page and ``errors="replace"`` hides that (the rule
        # tests/test_subprocess_decoding.py enforces on every capture).
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    out = (probe.stdout or "") + (probe.stderr or "")
    hit = _COLLECTED.search(out)
    return (int(hit.group(1)) if hit else -1), out


def test_the_pinned_reading_is_the_count_this_tree_collects() -> None:
    for doc_name, files in PINS:
        reading = recorded_reading(REPO / doc_name, files)
        assert reading is not None, f"{doc_name} stopped carrying a reading for {files}"
        command, recorded = reading
        collected, out = collected_count(files)
        assert collected > 0, f"the recorded command collects nothing now: {command}\n{out[-800:]}"
        assert recorded == collected, (
            f"{doc_name} pins {recorded} cases for `{command}` while this tree collects "
            f"{collected}; refill that line from a fresh run - the document says so itself"
        )


def test_the_pin_table_names_files_that_are_still_there() -> None:
    assert PINS, "the pin table is empty, so this gate guards nothing"
    for doc_name, files in PINS:
        assert (REPO / doc_name).is_file(), f"the pinned document is gone: {doc_name}"
        for name in files:
            assert (REPO / name).is_file(), f"the pinned command names a file that is gone: {name}"


def test_the_matcher_is_keyed_on_the_files_and_not_on_any_pytest_block(tmp_path: Path) -> None:
    """Reverse control: a block naming other files must not satisfy this pin."""
    doc = tmp_path / "planted.md"
    doc.write_text(
        "```powershell\npython -m pytest tests/test_some_other_file.py -q\n```\n\n"
        "复现结果：`7 passed in 1.0s`。\n",
        encoding="utf-8",
    )
    files = PINS[0][1]
    assert recorded_reading(doc, files) is None
    assert recorded_reading(doc, ("tests/test_some_other_file.py",)) == (
        "python -m pytest tests/test_some_other_file.py -q", 7)


def test_a_stale_reading_is_visible_to_the_same_comparison(tmp_path: Path) -> None:
    """Reverse control: one case off, on the real files, must read as a mismatch."""
    files = PINS[0][1]
    collected, _ = collected_count(files)
    assert collected > 0
    doc = tmp_path / "planted.md"
    doc.write_text(
        "```powershell\npython -m pytest " + " ".join(files) + " -q\n```\n\n"
        f"复现结果：`{collected - 1} passed in 1.0s`。\n",
        encoding="utf-8",
    )
    reading = recorded_reading(doc, files)
    assert reading is not None and reading[1] == collected - 1, reading
    assert reading[1] != collected


def test_a_document_that_lost_the_reading_answers_none(tmp_path: Path) -> None:
    """The ``None`` branch is a failure upstairs, so it has to be reachable."""
    files = PINS[0][1]
    doc = tmp_path / "planted.md"
    doc.write_text(
        "```powershell\npython -m pytest " + " ".join(files) + " -q\n```\n\n"
        "本次没有记录读数。\n",
        encoding="utf-8",
    )
    assert recorded_reading(doc, files) is None


def test_a_sentence_that_lost_the_pytest_tail_is_not_a_reading(tmp_path: Path) -> None:
    """The pin claims to be the verbatim tail of a run, so the shape is part of it."""
    files = PINS[0][1]
    doc = tmp_path / "planted.md"
    doc.write_text(
        "```powershell\npython -m pytest " + " ".join(files) + " -q\n```\n\n"
        "复现结果：全部用例通过。\n",
        encoding="utf-8",
    )
    assert recorded_reading(doc, files) is None
