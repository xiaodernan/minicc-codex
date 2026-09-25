"""M8-T57: a text-mode subprocess capture must never be decoded strictly.

The class, in one sentence: ``subprocess.run(..., text=True)`` with no ``errors``
handler decodes the child's bytes with the *parent's* locale codec, and when a
byte is invalid there the exception is raised inside subprocess's own reader
thread. ``run`` itself still returns ``returncode=0`` - with stdout swallowed to
an empty string - so the caller silently loses the whole stream.

Two measurements from the run that registered this batch:

  * ``git log --format=%s`` in this repository produced 739 bytes, 291 of them
    above 0x7F; the same call through ``text=True`` and no handler returned
    ``rc=0`` and zero characters.
  * the bench grader host (``minicc/bench_tasks.py``, ``_run_grader``) lost its
    ``MINICC_COMMAND_CONTRACT_COMPLETE`` marker line the same way as soon as the
    graded command echoed a non-ASCII message - which is how a correct workspace
    gets graded as failed.

A third measurement decided this gate's domain. The full suite run without
``PYTHONIOENCODING`` reddened two gates of *the documentation gate itself*
(``tests/test_doc_pointers.py``, which pins ``encoding="utf-8"`` but no handler,
around a child that writes the machine code page): the checker's summary line
contains one non-ASCII pair of brackets, and that was enough to swallow the
whole report - so ``assert "DANGLING" not in result.stdout`` was reading
``None``. A gate whose green depends on an environment variable nobody is
required to set is not a gate, so ``scripts/`` and ``tests/`` are in scope here
too, not just ``minicc/``.

The remedy is the shape ``minicc/tools/git.py`` already uses: declare a lossy
handler, and name the codec when the producer is known. ``decode_process_output``
in ``minicc/tools/bash.py`` documents the same rule for bytes ("Decode command
output without crashing on a Windows code page"), which is why the promise itself
is not enough to enforce - only the call sites are.

Gate shape notes:

  * the inventory comes from the AST, not from grep: a grep for ``capture_output``
    cannot tell bytes mode from text mode, and bytes mode cannot mis-decode;
  * the bench graders ship as Python *source inside a string constant*, so a
    file-level AST never sees the calls in them. Those constants are parsed and
    scanned too, and a synthetic case pins that the extra pass is load-bearing;
  * every "the list is empty" assertion is paired with a witness that the scanner
    can still see a planted violation, so a broken scanner cannot read as a pass;
  * this file is excluded from its own inventory - it is the one place a violating
    call is written on purpose - which also means the gate cannot catch a real
    text-mode capture added *here*; the module carries no such capture.
"""

from __future__ import annotations

import ast
import locale
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
#: Everything that ships or gates: the package, the repo's own gate scripts, and
#: the test harnesses that parse subprocess output (see the module docstring for
#: why the third one is not exempt).
SCAN_ROOTS = (REPO / "minicc", REPO / "scripts", REPO / "tests")

#: Only calls that hand output back as text can mis-decode it.
ENTRY_POINTS = frozenset({"run", "Popen", "check_output", "check_call"})

#: Counted on the tree that registered this batch (29 text-mode captures across
#: the three roots, 2 of them inside embedded grader scripts). A drop means the
#: scanner stopped seeing part of the inventory - the shape that made an earlier
#: empty inventory read as a green pass.
_MIN_TEXT_CAPTURES = 29
_MIN_EMBEDDED_CAPTURES = 2

_LOCALE_IS_UTF8 = "utf" in locale.getpreferredencoding(False).lower()


class Capture:
    """One subprocess call, as the AST saw it."""

    def __init__(self, origin: str, node: ast.Call, source: str) -> None:
        self.origin = origin
        self.node = node
        self.line = node.lineno
        self.callee = str(getattr(node.func, "attr", None) or getattr(node.func, "id", None))
        self.keywords = {keyword.arg: keyword.value for keyword in node.keywords if keyword.arg}
        self.segment = ast.get_source_segment(source, node) or ""

    @property
    def text_mode(self) -> bool:
        return self._true_constant("text") or self._true_constant("universal_newlines")

    @property
    def has_errors(self) -> bool:
        return "errors" in self.keywords

    @property
    def encoding(self) -> object:
        node = self.keywords.get("encoding")
        return node.value if isinstance(node, ast.Constant) else None

    @property
    def runs_git(self) -> bool:
        """True when the command being run starts with the literal ``git``."""

        head = self._command_head()
        return isinstance(head, ast.Constant) and (head.value == "git" or str(head.value).startswith("git "))

    @property
    def runs_python(self) -> bool:
        """True when the command being run starts with ``sys.executable``.

        That is the shape where both ends are ours to declare: the child's stdio
        codec follows ``PYTHONIOENCODING``, so a parent that pins a decoder
        without saying so is half a fix - it converts a crash into mojibake,
        which still breaks any assertion that reads non-ASCII out of the report.
        """

        head = self._command_head()
        return (
            isinstance(head, ast.Attribute)
            and head.attr == "executable"
            and getattr(head.value, "id", "") == "sys"
        )

    @property
    def declares_child_codec(self) -> bool:
        return "PYTHONIOENCODING" in self.segment

    def _command_head(self) -> ast.expr | None:
        if not self.node.args:
            return None
        first = self.node.args[0]
        if isinstance(first, ast.List) and first.elts:
            return first.elts[0]
        return first

    def _true_constant(self, name: str) -> bool:
        node = self.keywords.get(name)
        return isinstance(node, ast.Constant) and bool(node.value)

    def label(self) -> str:
        return f"{self.origin}:{self.line} subprocess.{self.callee}"


def _captures_from_tree(tree: ast.AST, origin: str, source: str) -> list[Capture]:
    found: list[Capture] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
        if callee not in ENTRY_POINTS:
            continue
        if isinstance(node.func, ast.Attribute):
            owner = getattr(node.func.value, "id", None) or getattr(node.func.value, "attr", None)
            if owner not in {"subprocess", "_subprocess"}:
                continue
        found.append(Capture(origin, node, source))
    return found


def _module_captures(path: Path, origin: str) -> list[Capture]:
    """Every subprocess call a module can make - including calls inside scripts.

    The file AST covers ordinary calls. Module-level strings that are valid
    Python are parsed as well: the bench graders are embedded scripts, and a
    scanner that stops at the file AST reports a clean inventory while the
    grader still crashes on a code page.
    """

    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    captures = _captures_from_tree(tree, origin, source)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if "subprocess." not in node.value:
            continue
        try:
            inner = ast.parse(node.value)
        except SyntaxError:
            continue
        captures.extend(_captures_from_tree(inner, f"{origin}#embedded@{node.lineno}", node.value))
    return captures


def scanned_captures() -> list[Capture]:
    """Every capture in the three roots, minus this file.

    This is the one place a violating call may be written on purpose - the
    planted witnesses below are such strings - so scanning it would redden the
    gate for holding the very text it uses to prove it can see a violation.
    """

    here = Path(__file__).resolve()
    captures: list[Capture] = []
    for root in SCAN_ROOTS:
        for path in sorted(root.rglob("*.py")):
            if path.resolve() == here:
                continue
            captures.extend(_module_captures(path, path.relative_to(REPO).as_posix()))
    return captures


def text_captures(captures: list[Capture]) -> list[Capture]:
    return [item for item in captures if item.text_mode]


def strict_text_captures(captures: list[Capture]) -> list[Capture]:
    return [item for item in captures if item.text_mode and not item.has_errors]


def git_captures_without_utf8(captures: list[Capture]) -> list[Capture]:
    return [
        item
        for item in text_captures(captures)
        if item.runs_git and str(item.encoding).lower().replace("-", "") != "utf8"
    ]


def utf8_pinned_python_children(captures: list[Capture]) -> list[Capture]:
    """Captures that already pinned the parent's decoder over a child we own."""

    return [
        item
        for item in text_captures(captures)
        if str(item.encoding).lower().replace("-", "") == "utf8" and item.runs_python
    ]


def codec_pin_mismatches(captures: list[Capture]) -> list[Capture]:
    return [item for item in utf8_pinned_python_children(captures) if not item.declares_child_codec]


SYNTHETIC_STRICT = "import subprocess\nsubprocess.run(['echo', 'hi'], capture_output=True, text=True)\n"
SYNTHETIC_LOSSY = (
    "import subprocess\n"
    "subprocess.run(['echo', 'hi'], capture_output=True, text=True, errors='replace')\n"
)
SYNTHETIC_GIT = (
    "import subprocess\n"
    "subprocess.run(['git', 'status'], capture_output=True, text=True, errors='replace')\n"
)
SYNTHETIC_BYTES = "import subprocess\nsubprocess.run(['git', 'status'], capture_output=True)\n"
SYNTHETIC_EMBEDDED = (
    "GRADER = '''\nimport subprocess\nproc = subprocess.run('make', shell=True, capture_output=True, text=True)\n'''\n"
)
SYNTHETIC_PYCHILD_HALF_PINNED = (
    "import subprocess, sys\n"
    "subprocess.run([sys.executable, 'x.py'], capture_output=True, text=True, encoding='utf-8', errors='replace')\n"
)
SYNTHETIC_PYCHILD_PINNED = (
    "import os, subprocess, sys\n"
    "subprocess.run(\n"
    "    [sys.executable, 'x.py'], capture_output=True, text=True, encoding='utf-8', errors='replace',\n"
    "    env=dict(os.environ, PYTHONIOENCODING='utf-8'),\n"
    ")\n"
)
SYNTHETIC_LOCALE_MATCHED = (
    "import subprocess, sys\n"
    "subprocess.run([sys.executable, 'x.py'], capture_output=True, text=True, errors='replace')\n"
)


def _scan_source(text: str) -> list[Capture]:
    with tempfile.TemporaryDirectory() as raw:
        module = Path(raw) / "synthetic.py"
        module.write_text(text, encoding="utf-8")
        return _module_captures(module, "synthetic.py")


def test_the_scanned_inventory_is_big_enough_to_be_the_real_one() -> None:
    """A gate over an empty list passes forever, so the list has to have a size."""

    captures = scanned_captures()
    assert len(text_captures(captures)) >= _MIN_TEXT_CAPTURES, len(text_captures(captures))
    embedded = [item for item in captures if "#embedded@" in item.origin]
    assert len(embedded) >= _MIN_EMBEDDED_CAPTURES, (
        "the embedded grader scripts fell out of view; the file AST alone cannot see them"
    )


def test_every_scan_root_still_contributes_to_the_inventory() -> None:
    """The floor alone cannot tell that two roots went blind while one stayed loud."""

    origins = {item.origin.split("/", 1)[0] for item in scanned_captures()}
    assert {"minicc", "scripts", "tests"} <= origins, origins


def test_no_text_mode_capture_asks_for_a_strict_decoder() -> None:
    offenders = [item.label() for item in strict_text_captures(scanned_captures())]
    assert offenders == [], f"text-mode captures that can swallow their own output: {offenders}"


def test_captures_of_git_output_name_the_codec() -> None:
    """git always emits UTF-8, so decoding it with the machine locale is wrong twice.

    Under a Chinese locale the path comes back as mojibake that still decodes,
    which is worse than a crash: the caller receives a plausible, wrong string.
    """

    offenders = [item.label() for item in git_captures_without_utf8(scanned_captures())]
    assert offenders == [], f"git captures not pinned to utf-8: {offenders}"


def test_a_pinned_parent_decoder_over_our_own_python_child_pins_the_child_too() -> None:
    """``encoding="utf-8"`` on one end alone converts a crash into mojibake.

    Measured in this batch: after the two checker captures got ``errors=``, the
    swallowed stream came back but ``re.search(r"(\\d+) 「见」 markers")`` returned
    ``None`` - the child had written the report in the machine code page. The
    gate that reads non-ASCII out of a report has to own both ends.
    """

    scanned = scanned_captures()
    domain = [item.label() for item in utf8_pinned_python_children(scanned)]
    assert len(domain) >= 1, "the rule's own domain went empty; it would pass forever"
    offenders = [item.label() for item in codec_pin_mismatches(scanned)]
    assert offenders == [], f"half-pinned captures (parent utf-8, child undeclared): {offenders}"


def test_the_scanner_sees_a_capture_that_omits_the_handler() -> None:
    """Without witnesses, 'no offenders' and 'broken scanner' read the same."""

    captured = _scan_source(SYNTHETIC_STRICT)
    assert len(captured) == 1, captured
    assert [item.label() for item in strict_text_captures(captured)] == ["synthetic.py:2 subprocess.run"]
    assert strict_text_captures(_scan_source(SYNTHETIC_LOSSY)) == [], "the rule must not be 'flag everything'"
    assert strict_text_captures(_scan_source(SYNTHETIC_BYTES)) == [], "bytes mode cannot mis-decode"


def test_the_scanner_tells_a_half_pinned_child_from_a_matched_pair() -> None:
    """The new rule needs both a red witness and a green one, or it is decoration.

    ``SYNTHETIC_LOCALE_MATCHED`` is the third shape: no codec named on either
    end, which is self-consistent (child and parent share the machine locale) and
    therefore not this rule's business - flagging it would push people toward
    pinning a decoder and reintroducing the mismatch.
    """

    half = _scan_source(SYNTHETIC_PYCHILD_HALF_PINNED)
    assert len(half) == 1, half
    assert [item.label() for item in codec_pin_mismatches(half)] == ["synthetic.py:2 subprocess.run"]
    assert utf8_pinned_python_children(half), "the domain predicate must see the half-pinned call"
    both = _scan_source(SYNTHETIC_PYCHILD_PINNED)
    assert len(both) == 1, both
    assert utf8_pinned_python_children(both), both
    assert codec_pin_mismatches(both) == [], "the compliant shape must not read as a violation"
    matched = _scan_source(SYNTHETIC_LOCALE_MATCHED)
    assert len(matched) == 1, matched
    assert codec_pin_mismatches(matched) == [], "no pin on either end is not a mismatch"


def test_the_scanner_sees_the_rule_break_inside_an_embedded_script() -> None:
    """The embedded pass is load-bearing: the file AST alone reports nothing here."""

    captured = _scan_source(SYNTHETIC_EMBEDDED)
    assert len(captured) == 1, captured
    assert "#embedded@" in captured[0].origin
    assert strict_text_captures(captured), captured
    git_only = _scan_source(SYNTHETIC_GIT)
    assert len(git_only) == 1
    assert [item.label() for item in git_captures_without_utf8(git_only)] == ["synthetic.py:2 subprocess.run"]


def test_an_undecodable_byte_does_not_swallow_the_rest_of_the_output(tmp_path: Path) -> None:
    """The production host must still read its own marker after a bad byte.

    0xFF and 0xFE are invalid in every codec in play (UTF-8, cp936, gb18030), so
    this reddens on a Chinese Windows and on an English one alike: it does not
    depend on the machine's locale, which is what makes it a usable witness.
    """

    from minicc import bench_tasks

    grader = (
        "import sys\n"
        "sys.stdout.buffer.write(b'\\xff\\xfe\\xff\\n')\n"
        "sys.stdout.flush()\n"
        "print('MINICC_SYNTHETIC_COMPLETE:1')\n"
    )
    result = bench_tasks._run_grader(
        "byte_probe.py",
        grader,
        tmp_path / "graders",
        tmp_path,
        {},
        isolated=False,
        timeout=60,
    )
    assert result.returncode == 0, result
    assert "MINICC_SYNTHETIC_COMPLETE:1" in (result.stdout or "").splitlines(), (
        f"the marker was lost with the rest of the stream; the host read {result.stdout!r}"
    )


#: ``{python}`` is rendered by the host; the bytes written first are invalid in
#: every codec in play, so the probe works the same on any machine locale.
_UNDECODABLE_THEN_MARKER = (
    "{python} -c "
    "\"import sys;"
    " sys.stdout.buffer.write(b'\\xff\\xfe\\xff\\n');"
    " print('MINICC_DECODING_PROBE')\""
)


def test_a_graded_command_that_emits_undecodable_bytes_is_not_graded_as_failed(
    tmp_path: Path,
) -> None:
    """The witness for the capture inside ``_COMMAND_CONTRACT_GRADER``.

    That call lives in a string constant, so only the embedded AST pass sees it
    - and the string is what the graded command actually runs, so a strict
    decoder there is not cosmetic: ``proc.stdout`` becomes ``None``, the
    ``stdout_contains`` check then fails, and the grader reports
    ``COMPLETE:0`` for a command that exited 0 with the right marker.
    """

    from minicc import bench_tasks

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    task = {
        "id": "undecodable-output",
        "grader": {
            "type": "command_contract",
            "command": _UNDECODABLE_THEN_MARKER,
            "expect_exit": 0,
            "stdout_contains": "MINICC_DECODING_PROBE",
            "timeout": 60,
        },
    }
    outcome = bench_tasks.grade_command_contract(
        task, workspace, grader_dir=tmp_path / ".graders"
    )
    assert outcome == {"passed": True, "grader_type": "command_contract", "exit_code": 0}, outcome


@pytest.mark.skipif(_LOCALE_IS_UTF8, reason="a UTF-8 locale cannot produce the mojibake half of this defect")
def test_a_non_ascii_worktree_path_survives_the_reader(tmp_path: Path) -> None:
    """``worktree list`` must hand back the path git printed, not a locale guess.

    Measured on the machine that registered this batch: the main worktree path
    came back two characters longer than it is, because four Chinese characters
    were decoded as six mojibake ones - a wrong answer that no exception marks.
    """

    from minicc.worktree import WorktreeManager

    repo = tmp_path / "工作区 项目"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], capture_output=True, check=True, timeout=120)
    entries = WorktreeManager(repo).list()
    assert len(entries) == 1, entries
    assert entries[0]["path"].endswith("工作区 项目"), entries[0]["path"]
