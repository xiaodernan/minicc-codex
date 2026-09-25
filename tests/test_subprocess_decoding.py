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

M8-T58 widened the same class one seam further, to the *verdict* rather than the
stream.  ``_COMMAND_CONTRACT_GRADER`` compares ``stdout_contains`` against text it
decoded with the machine locale while the graded command wrote with whatever
``PYTHONIOENCODING`` the suite host happened to carry.  Measured for one correct
workspace that prints a Chinese line: ``passed`` with no ``PYTHONIOENCODING``,
``failed`` with ``PYTHONIOENCODING=utf-8``, i.e. the criterion was reading the
environment.  Two additions follow from that: a behavioral gate that grades the
same workspace under three parent codecs and requires the same verdict three
times, and a structural rule for embedded grader scripts, where "name no codec on
either end" is not a safe shape because the ambient environment names one for us.
"""

from __future__ import annotations

import ast
import io
import json
import locale
import re
import subprocess
import tempfile
import tokenize
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

#: ``PYTHONIOENCODING`` reaching an assignment, a ``dict(...)`` keyword or a
#: subscript store - the shapes that actually set a child's codec.
_CHILD_CODEC_ASSIGNMENT = re.compile(r"""PYTHONIOENCODING["'\s\]]{0,4}=""")


def _code_only(source: str) -> str:
    """``source`` with its comments blanked out, line structure preserved.

    A prose claim is not an implementation.  The first version of the embedded
    grader rule asked only whether the text ``PYTHONIOENCODING`` appeared
    somewhere in the script, and M8-T58's mutation M2 - delete the env pin, keep
    the comment that explains why the pin belongs there - stayed green under it.
    A half-finished fix is exactly the case where the words are present and the
    code is not, so a gate may not read the words.
    """

    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return source
    lines = source.splitlines(keepends=True)
    for token in reversed(tokens):
        if token.type != tokenize.COMMENT:
            continue
        (start_row, start_col), (_end_row, end_col) = token.start, token.end
        index = start_row - 1
        if 0 <= index < len(lines):
            line = lines[index]
            lines[index] = line[:start_col] + line[end_col:]
    return "".join(lines)


class Capture:
    """One subprocess call, as the AST saw it."""

    def __init__(self, origin: str, node: ast.Call, code: str) -> None:
        self.origin = origin
        self.node = node
        self.line = node.lineno
        self.code = code
        self.callee = str(getattr(node.func, "attr", None) or getattr(node.func, "id", None))
        self.keywords = {keyword.arg: keyword.value for keyword in node.keywords if keyword.arg}
        self.segment = ast.get_source_segment(code, node) or ""

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
    def pins_utf8(self) -> bool:
        return str(self.encoding).lower().replace("-", "") == "utf8"

    @property
    def in_embedded_script(self) -> bool:
        """True for calls the scanner reached through a source-carrying string.

        An embedded grader's own ``source`` is the script text, so a codec
        declaration anywhere in it is in scope for the calls inside it - which is
        the tightest scope this instrument can address for a ``shell=True`` child
        it cannot resolve.
        """

        return "#embedded@" in self.origin

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

    @property
    def declares_child_codec_in_source(self) -> bool:
        """Whether the script this call lives in *assigns* the child's codec.

        The segment-scoped version above cannot serve a ``shell=True`` child: the
        env it hands the command is built on its own line, outside the call.  The
        scope here is the whole script - which for an embedded grader is exactly
        the file the child runs - and the test is an assignment shape over
        comment-stripped text, because the M8-T58 comment explaining the pin must
        not be able to stand in for the pin (see ``_code_only``).
        """

        return bool(_CHILD_CODEC_ASSIGNMENT.search(self.code))

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


def _captures_from_tree(tree: ast.AST, origin: str, code: str) -> list[Capture]:
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
        found.append(Capture(origin, node, code))
    return found


def _module_captures(path: Path, origin: str) -> list[Capture]:
    """Every subprocess call a module can make - including calls inside scripts.

    The file AST covers ordinary calls. Module-level strings that are valid
    Python are parsed as well: the bench graders are embedded scripts, and a
    scanner that stops at the file AST reports a clean inventory while the
    grader still crashes on a code page.

    Predicates that read text rather than nodes see ``_code_only(...)`` output, so
    a comment can never satisfy a rule about code.
    """

    source = path.read_text(encoding="utf-8")
    code = _code_only(source)
    tree = ast.parse(source, filename=str(path))
    captures = _captures_from_tree(tree, origin, code)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if "subprocess." not in node.value:
            continue
        try:
            inner = ast.parse(node.value)
        except SyntaxError:
            continue
        captures.extend(
            _captures_from_tree(
                inner, f"{origin}#embedded@{node.lineno}", _code_only(node.value)
            )
        )
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


def embedded_grader_captures(captures: list[Capture]) -> list[Capture]:
    """Text-mode captures that read a command the grader itself does not own.

    This is the command-contract shape: ``subprocess.run(command, shell=True)``
    inside a script string. The child is whatever the task says, and in this repo
    that is normally ``{python}`` rendered onto an interpreter - so the child's
    stdout codec follows ``PYTHONIOENCODING``, exactly as in the
    ``sys.executable`` case above. It cannot be detected from the call head, so
    the embedded-script origin is the discriminator.

    Unlike the ``sys.executable`` rule, "name nothing on either end" is *not* an
    accepted shape here: the reader then follows the machine locale while the
    writer follows whatever ``PYTHONIOENCODING`` the ambient environment happens
    to carry, and M8-T58 measured a correct workspace graded as failed because of
    it. Only a pair is stable.
    """

    return [item for item in text_captures(captures) if item.in_embedded_script]


def embedded_grader_unpaired_codec(captures: list[Capture]) -> list[Capture]:
    return [
        item
        for item in embedded_grader_captures(captures)
        if not (item.pins_utf8 and item.declares_child_codec_in_source)
    ]


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
#: The three shapes of an embedded grader's capture of a ``shell=True`` child.
#: ``_UNPAIRED`` is what shipped through M8-T57 (lossy handler, no codec named);
#: ``_HALF_PINNED`` is the one-sided repair that converts a crash into mojibake;
#: ``_PINNED`` is the pair, which is what the production grader now carries.
SYNTHETIC_EMBEDDED_UNPAIRED = (
    "GRADER = '''\n"
    "import subprocess\n"
    "proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, errors='replace')\n"
    "'''\n"
)
SYNTHETIC_EMBEDDED_HALF_PINNED = (
    "GRADER = '''\n"
    "import os, subprocess\n"
    "env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')\n"
    "proc = subprocess.run(cmd, shell=True, capture_output=True, text=True,\n"
    "                      encoding='utf-8', errors='replace', env=env)\n"
    "'''\n"
)
SYNTHETIC_EMBEDDED_PINNED = (
    "GRADER = '''\n"
    "import os, subprocess\n"
    "env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')\n"
    "proc = subprocess.run(cmd, shell=True, capture_output=True, text=True,\n"
    "                      encoding='utf-8', errors='replace', env=env)\n"
    "'''\n"
)
#: The shape mutation M2 produced: the pin is gone from the code and the sentence
#: that justifies it is still there.  This is what a half-revert of the fix looks
#: like in a real file, so it is the case the instrument must not read as clean.
SYNTHETIC_EMBEDDED_COMMENTED_PIN = (
    "GRADER = '''\n"
    "import os, subprocess\n"
    "# PYTHONIOENCODING='utf-8' pins the child to the decoder named below.\n"
    "env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')\n"
    "proc = subprocess.run(cmd, shell=True, capture_output=True, text=True,\n"
    "                      encoding='utf-8', errors='replace', env=env)\n"
    "'''\n"
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


#: The marker the graded command prints.  Non-ASCII on purpose: an ASCII marker
#: cannot separate "the parent decoded what the child wrote" from "both sides
#: happened to guess the same machine codec", which is the whole defect.
_NON_ASCII_MARKER = "构建完成"
_PRINTS_NON_ASCII_MARKER = '{python} -c "print(\'构建完成\')"'

#: The three parent environments a bench run can start under.  ``None`` means
#: "the suite host's own environment, untouched", which is what CI gets; the two
#: named codecs are what a developer gets after setting the variable once to fix
#: some unrelated mojibake.  On any machine at least one of the three disagrees
#: with the machine locale, so this trio reddens on a cp936 host (where
#: ``utf-8`` is the odd one) and on a UTF-8 host (where ``cp936`` is) alike - a
#: single pair would only catch one of the two.
_PARENT_CODECS: tuple[str | None, ...] = (None, "utf-8", "cp936")


def _grade_command_under_parent_codecs(
    monkeypatch, tmp_path: Path, command: str, marker: str, grader_dir_name: str
) -> dict[str, dict[str, object]]:
    """Grade one fixed workspace once per parent ``PYTHONIOENCODING`` setting."""

    from minicc import bench_tasks

    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    task = {
        "id": "non-ascii-verdict",
        "grader": {
            "type": "command_contract",
            "command": command,
            "expect_exit": 0,
            "stdout_contains": marker,
            "timeout": 60,
        },
    }
    outcomes: dict[str, dict[str, object]] = {}
    for parent_codec in _PARENT_CODECS:
        if parent_codec is None:
            monkeypatch.delenv("PYTHONIOENCODING", raising=False)
        else:
            monkeypatch.setenv("PYTHONIOENCODING", parent_codec)
        outcomes[str(parent_codec)] = bench_tasks.grade_command_contract(
            task, workspace, grader_dir=tmp_path / grader_dir_name
        )
    return outcomes


def test_a_non_ascii_command_verdict_does_not_move_with_the_parent_environment(
    monkeypatch, tmp_path: Path
) -> None:
    """The criterion has to measure the work, not the shell that ran the suite.

    Measured on the cp936 machine that registered this batch, for a workspace
    whose graded command is ``print('构建完成')`` and whose ``stdout_contains`` is
    that same string - i.e. correct work, by the task's own definition:

      * no ``PYTHONIOENCODING`` in the parent environment -> ``passed: True``
      * ``PYTHONIOENCODING=utf-8`` in the parent environment -> ``passed: False``
      * ``PYTHONIOENCODING=cp936`` in the parent environment -> ``passed: True``

    Nothing about the work changed. The child's writer followed the environment
    variable, the grader's reader stayed on the machine locale, and the marker
    came back as mojibake - so a bench score moved because a developer was
    fixing an unrelated encoding bug in their profile.
    """

    outcomes = _grade_command_under_parent_codecs(
        monkeypatch, tmp_path, _PRINTS_NON_ASCII_MARKER, _NON_ASCII_MARKER, ".graders-cmd",
    )
    assert outcomes == {
        "None": {"passed": True, "grader_type": "command_contract", "exit_code": 0},
        "utf-8": {"passed": True, "grader_type": "command_contract", "exit_code": 0},
        "cp936": {"passed": True, "grader_type": "command_contract", "exit_code": 0},
    }, outcomes


def test_a_non_ascii_file_contract_verdict_is_stable_because_the_spec_travels_as_ascii(
    monkeypatch, tmp_path: Path
) -> None:
    """The neighbouring seam, pinned as *not* the defect - with its real reason.

    This one was green before the M8-T58 patch and stays green, and the reason is
    worth recording rather than assuming: the file grader never reads the
    candidate's stdout, it reads files with ``encoding="utf-8"`` itself, and the
    spec is handed over as ``json.dumps`` output, whose default
    ``ensure_ascii=True`` escapes the marker to ``\\u6784\\u5efa...``.  Pure ASCII
    survives any codec on either end.  So the safety here is the transport, not
    the shape of the seam: dropping ``ensure_ascii`` would make the same Chinese
    marker cross a locale boundary in the other direction.
    """

    from minicc import bench_tasks

    workspace = tmp_path / "workspace"
    (workspace / "out").mkdir(parents=True)
    (workspace / "out" / "report.md").write_text("结果：构建完成\n", encoding="utf-8")
    task = {
        "id": "non-ascii-file",
        "grader": {
            "type": "file_contract",
            "files": [{"path": "out/report.md", "contains": _NON_ASCII_MARKER}],
            "timeout": 60,
        },
    }
    # The transport claim, asserted rather than narrated.
    spec = task["grader"]
    assert json.dumps(spec).isascii(), json.dumps(spec)
    assert not json.dumps(spec, ensure_ascii=False).isascii()

    outcomes: dict[str, dict[str, object]] = {}
    for parent_codec in _PARENT_CODECS:
        if parent_codec is None:
            monkeypatch.delenv("PYTHONIOENCODING", raising=False)
        else:
            monkeypatch.setenv("PYTHONIOENCODING", parent_codec)
        outcomes[str(parent_codec)] = bench_tasks.grade_file_contract(
            task, workspace, grader_dir=tmp_path / ".graders-file"
        )
    assert [item["passed"] for item in outcomes.values()] == [True, True, True], outcomes


def test_an_embedded_grader_names_the_codec_on_both_ends() -> None:
    """``encoding="utf-8"`` alone is half a fix, and silence is not a fix at all.

    The ``sys.executable`` rule above cannot reach this shape: the call head is a
    variable holding the task's own command, so no predicate on it can tell that
    the child is a Python interpreter.  The bench renders ``{python}`` onto
    ``sys.executable``, so the child's stdio codec does follow
    ``PYTHONIOENCODING`` all the same, and "name nothing on either end" is not an
    accepted shape here because the ambient environment can name one half for us.
    """

    scanned = scanned_captures()
    domain = [item.label() for item in embedded_grader_captures(scanned)]
    assert len(domain) >= 1, (
        "the embedded text-mode captures went empty; the scanner lost the bench graders"
    )
    offenders = [item.label() for item in embedded_grader_unpaired_codec(scanned)]
    assert offenders == [], f"embedded captures without a declared pair: {offenders}"


def test_the_scanner_sees_an_embedded_capture_that_pins_only_its_own_reader() -> None:
    """Both red witnesses and the green one, or the rule above is decoration.

    ``SYNTHETIC_EMBEDDED_UNPAIRED`` is the shape that shipped for a batch and a
    half - a lossy handler, no codec named anywhere.  It is the one the
    ``sys.executable`` rule deliberately ignores ("self-consistent, both ends on
    the machine locale"), and the reason it cannot be ignored inside a grader is
    in the docstring of the gate above: the grader's child inherits an environment
    the suite host controls.
    """

    half = _scan_source(SYNTHETIC_EMBEDDED_HALF_PINNED)
    assert len(half) == 1, half
    assert [item.label() for item in embedded_grader_unpaired_codec(half)] == [
        "synthetic.py#embedded@1:4 subprocess.run"
    ], half
    silent = _scan_source(SYNTHETIC_EMBEDDED_UNPAIRED)
    assert len(silent) == 1, silent
    assert [item.label() for item in embedded_grader_unpaired_codec(silent)] == [
        "synthetic.py#embedded@1:3 subprocess.run"
    ], silent
    paired = _scan_source(SYNTHETIC_EMBEDDED_PINNED)
    assert len(paired) == 1, paired
    assert embedded_grader_captures(paired), "the compliant shape must still be in the rule's domain"
    assert embedded_grader_unpaired_codec(paired) == [], paired


def test_a_comment_about_the_codec_pin_does_not_satisfy_the_pin_rule() -> None:
    """The instrument's own hole, found by mutation M2 and closed here.

    ``SYNTHETIC_EMBEDDED_COMMENTED_PIN`` is what the fix looks like after someone
    reverts the env assignment and leaves the explanatory sentence behind.  The
    first version of the rule searched the script's text, so that file read as
    compliant and only the behavioral gate went red - which is the right outcome
    for a behavioral claim but the wrong one for a structural claim, since it
    means the structural gate has no coverage on a machine where the behavioral
    one happens to be skipped.
    """

    assert "PYTHONIOENCODING" in SYNTHETIC_EMBEDDED_COMMENTED_PIN
    # The mechanism, stated once without going through the scanner at all: the
    # comment goes, the line structure stays, and an assignment survives.
    assert _code_only("x = 1  # PYTHONIOENCODING='utf-8'\ny = 2\n") == "x = 1  \ny = 2\n"
    assert _CHILD_CODEC_ASSIGNMENT.search(
        _code_only("env = dict(os.environ, PYTHONIOENCODING='utf-8')\n")
    ), "the strip must not blind the rule to the shape it exists to find"

    commented = _scan_source(SYNTHETIC_EMBEDDED_COMMENTED_PIN)
    assert len(commented) == 1, commented
    assert [item.label() for item in embedded_grader_unpaired_codec(commented)] == [
        "synthetic.py#embedded@1:5 subprocess.run"
    ], commented
    # The production grader carries both a long comment and the real assignment;
    # it must still read as paired, or the strip is over-broad.
    production = [
        item
        for item in embedded_grader_captures(scanned_captures())
        if "bench_tasks.py" in item.origin
    ]
    assert len(production) == 1, production
    assert production[0].declares_child_codec_in_source, production[0].code
    assert embedded_grader_unpaired_codec(production) == []


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
