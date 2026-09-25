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

M8-T60 took the last thing this file still delegated to the machine.  One gate here
was written as ``skipif(host locale is UTF-8)`` on the theory that a UTF-8 host
cannot produce a codec mismatch - true of the *host*, and therefore a gate that ran
nowhere on CI (measured: with ``PYTHONUTF8=1`` the shipped version reports
``1 skipped``).  The rewrite drops the skip and asserts the invariant instead of the
incident: git's own bytes say what a path is, and production's answer must equal
those bytes read as UTF-8.  That is checkable on every host, and it covers a class
the keyword-shape rule above cannot see at all - right kwarg, wrong answer.
Two claims died in the measuring, and they are recorded here rather than quietly
dropped: a text-mode reader's *default* codec is not taken from
``locale.getpreferredencoding`` at call time (patching it, and patching
``io.text_encoding``, which answers ``'locale'`` for ``None``, moved the decoding on
neither a cp936 host nor a UTF-8-mode one), so a test cannot manufacture a codec
mismatch at will; and a *writer's* codec can be, which is what makes M8-T58's
three-parent-codec gate work wherever it runs.  Consequence, measured on both hosts:
deleting the worktree pin reddens the structural git rule everywhere but reddens the
behavioral gate only on a host whose default is not UTF-8.
"""

from __future__ import annotations

import ast
import io
import json
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

#: Counted on the tree that registered M8-T60: 14 text-mode captures whose child is
#: git, every one of them pinned. The offenders list is empty by two possible causes
#: - nothing violates, or ``runs_git`` sees nothing - and only this floor tells them
#: apart.
_MIN_GIT_CAPTURES = 14

#: A codec that is always the wrong answer for the bytes git writes, and one of
#: Python's built-ins, so it is present on every platform.  It is named explicitly
#: rather than inherited from the machine: the reading it produces is the comparison
#: the worktree gates below need, and a gate may not depend on which code page the
#: host happens to carry.
_ALIEN_READER_CODEC = "cp936"

#: A directory name that cannot survive a wrong reader codec: these UTF-8 bytes read
#: as ``_ALIEN_READER_CODEC`` come back as different characters, which is the shape
#: the worktree gates count on.  That it stays true is itself gated
#: (``test_the_alien_reader_is_the_one_that_disagrees``), because an accidentally
#: ASCII-only fixture would make every claim above it vacuous.
_NON_ASCII_DIR = "工作区 项目"

#: Production text-mode captures that name no codec on the reader's end, each with a
#: proof this file checks rather than a sentence it is asked to trust:
#:
#:   ``ascii-marker:NAME`` - the only text that has to cross this boundary is the
#:   literal ``NAME``, and the string piece carrying it must still be pure ASCII;
#:   ``no-consumer:NAME`` - the object the call is bound to is never read for
#:   ``stdout`` or ``stderr``, so nothing decoded here reaches anything.
#:
#: Keyed by call site on purpose: moving or renaming a capture voids its exemption and
#: makes the next reader re-earn it, the same friction ``doc_pointers.py`` applies to
#: its own exemption table.
_VERDICT_NEUTRAL_CAPTURES: dict[str, list[str]] = {
    "minicc/behavior_bench.py:105 subprocess.run": ["ascii-marker:MINICC_BEHAVIOR_COMPLETE"],
    "minicc/bench_tasks.py:229 subprocess.run": [
        "ascii-marker:MINICC_FILE_CONTRACT_COMPLETE",
        "ascii-marker:MINICC_COMMAND_CONTRACT_COMPLETE",
    ],
    "minicc/benchmarks.py:661 subprocess.run": ["no-consumer:completed"],
}

#: Production text-mode captures - the domain of the exemption rule below.  13 of
#: the 29 counted above ship; of the 7 that name no reader codec, 3 are under
#: ``minicc/`` and are that rule's whole content, and 4 are test harnesses, where a
#: wrong read shows up as a red gate instead of as a wrong answer handed to a user.
#: The split is by failure mode, not by importance: M8-T57's handler rule still
#: covers all three roots.
_MIN_PRODUCTION_TEXT_CAPTURES = 13

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


def _string_pieces(text: str) -> list[str] | None:
    """Every string literal in ``text``, f-string parts included.

    Pieces rather than expressions: an f-string's parts are separate constants,
    and what has to survive a codec boundary is the bytes one literal carries.
    ``None`` means the text would not parse, which a caller must report as
    "unverifiable" - never as "holds".
    """

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def _proof_context(capture: Capture) -> tuple[ast.AST, ast.Call] | None:
    """``(tree, call node)`` for a capture, from the source the scanner kept.

    ``capture.node`` cannot be reused: it belongs to the parse of the *commented*
    file, so the two trees share no objects and position is the only available
    identity.  A position resolving to zero or two calls yields ``None`` instead
    of a guess - an exemption checked against the wrong call is worse than none,
    because it reads as a pass.
    """

    try:
        tree = ast.parse(capture.code)
    except SyntaxError:
        return None
    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and node.lineno == capture.node.lineno
        and node.col_offset == capture.node.col_offset
    ]
    if len(found) != 1:
        return None
    return tree, found[0]


def _bound_to(tree: ast.AST, call: ast.Call) -> str | None:
    """The single name this call's result was assigned to, if it was assigned."""

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and node.value is call:
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                return node.targets[0].id
            return None
        if isinstance(node, ast.AnnAssign) and node.value is call and isinstance(node.target, ast.Name):
            return node.target.id
    return None


def _attribute_reads(tree: ast.AST, name: str) -> set[str]:
    """Attribute names read off a bare ``name`` anywhere in ``tree``."""

    return {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == name
    }


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


def git_captures(captures: list[Capture]) -> list[Capture]:
    """Text-mode calls whose child is git: the rule's domain, not its offenders."""

    return [item for item in text_captures(captures) if item.runs_git]


def git_captures_without_utf8(captures: list[Capture]) -> list[Capture]:
    return [item for item in git_captures(captures) if not item.pins_utf8]


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


def production_captures(captures: list[Capture]) -> list[Capture]:
    """Calls that ship, as opposed to calls that only ever run at test time.

    The domain of the exemption rule below, and the reason it is this domain and
    not all three roots is in ``_MIN_PRODUCTION_TEXT_CAPTURES``.
    """

    return [item for item in captures if item.origin.startswith("minicc/")]


def unpinned_outside_the_table(
    captures: list[Capture], table: dict[str, list[str]] = _VERDICT_NEUTRAL_CAPTURES
) -> list[Capture]:
    """Production text-mode captures that name no reader codec and claim no exemption.

    ``pins_utf8`` rather than "names a codec at all": a capture pinned to some
    other codec is not covered by this rule either, and leaving it out of both the
    pin and the table must not read as compliant.
    """

    return [
        item
        for item in text_captures(production_captures(captures))
        if not item.pins_utf8 and item.label() not in table
    ]


def _proof_failure(capture: Capture, proof: str) -> str | None:
    """Why ``proof`` does not hold for ``capture``, or ``None`` when it does."""

    kind, _, name = proof.partition(":")
    pieces = _string_pieces(capture.code)
    if kind == "ascii-marker":
        if pieces is None:
            return "the source does not parse, so the marker cannot be checked"
        carriers = [piece for piece in pieces if name in piece]
        if not carriers:
            return f"nothing on this seam carries {name!r}"
        non_ascii = [piece for piece in carriers if not piece.isascii()]
        if non_ascii:
            return f"{name!r} travels beside non-ASCII text: {non_ascii[0]!r}"
        return None
    if kind == "no-consumer":
        context = _proof_context(capture)
        if context is None:
            return "the source does not parse, or this call is not uniquely located in it"
        tree, node = context
        if _bound_to(tree, node) != name:
            return f"this call's result is not bound to {name!r}"
        read = {"stdout", "stderr"} & _attribute_reads(tree, name)
        if read:
            return f"{name}.{sorted(read)[0]} is read"
        return None
    return f"unknown proof shape {proof!r}"


def exemption_failures(
    captures: list[Capture], table: dict[str, list[str]] = _VERDICT_NEUTRAL_CAPTURES
) -> list[str]:
    """Why each entry of the exemption table does, or does not, still hold.

    Three independent ways an exemption rots, each checked here:

      * the call site moves or gets pinned, so the key is dead weight - the next
        reader would inherit a claim about code that no longer exists;
      * the proof it carries stops holding (the marker grows non-ASCII text, or
        somebody starts reading the stream it claims nobody consumes);
      * the proof cannot be checked at all, which counts as a failure.

    A key with an empty proof list is a sentence, and this file's rule about
    sentences is in ``_code_only``.
    """

    table = _VERDICT_NEUTRAL_CAPTURES if table is None else table
    production = text_captures(production_captures(captures))
    failures: list[str] = []
    for label, proofs in table.items():
        matches = [item for item in production if item.label() == label]
        if len(matches) != 1:
            failures.append(f"{label}: {len(matches)} production text-mode captures here")
            continue
        capture = matches[0]
        if capture.pins_utf8:
            failures.append(f"{label}: the reader is pinned now, so the exemption is dead weight")
        if not proofs:
            failures.append(f"{label}: an exemption with no proof is a sentence")
        for proof in proofs:
            failure = _proof_failure(capture, proof)
            if failure is not None:
                failures.append(f"{label}: {proof} -> {failure}")
    return failures


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


#: Production-shaped sources for the exemption table's witnesses.  The rule's
#: domain is decided by the origin (a capture that *ships*), so these are scanned
#: under ``minicc/``, and every one of them keeps its capture on line 2 so a single
#: label can name it.  The marker literal comes after the call on purpose: the
#: proof reads the whole module, so the order must not matter - and if it did, that
#: would be a hole in the proof rather than a reason to write the fixture again.
_SYNTHETIC_PRODUCTION_UNPINNED = (
    "import subprocess\n"
    "out = subprocess.run(cmd, capture_output=True, text=True, errors='replace')\n"
)
_SYNTHETIC_PRODUCTION_ASCII_MARKER = (
    "import subprocess\n"
    "out = subprocess.run(cmd, capture_output=True, text=True, errors='replace')\n"
    "MARKER = 'MINICC_PLANTED_COMPLETE'\n"
)
#: The proof that rotted: the marker still travels, but it now travels beside text
#: that cannot survive a codec mismatch, so "only ASCII crosses" is false.
_SYNTHETIC_PRODUCTION_NON_ASCII_MARKER = (
    "import subprocess\n"
    "out = subprocess.run(cmd, capture_output=True, text=True, errors='replace')\n"
    "MARKER = '构建完成 MINICC_PLANTED_COMPLETE'\n"
)
#: And here somebody started reading the stream the exemption claimed nobody
#: consumes.
_SYNTHETIC_PRODUCTION_CONSUMED = (
    "import subprocess\n"
    "completed = subprocess.run(cmd, capture_output=True, text=True, errors='replace')\n"
    "print(completed.stdout)\n"
)
_PLANTED = "minicc/planted.py:2 subprocess.run"


def _scan_source(text: str, origin: str = "synthetic.py") -> list[Capture]:
    with tempfile.TemporaryDirectory() as raw:
        module = Path(raw) / "synthetic.py"
        module.write_text(text, encoding="utf-8")
        return _module_captures(module, origin)


def test_the_scanned_inventory_is_big_enough_to_be_the_real_one() -> None:
    """A gate over an empty list passes forever, so the list has to have a size."""

    captures = scanned_captures()
    assert len(text_captures(captures)) >= _MIN_TEXT_CAPTURES, len(text_captures(captures))
    embedded = [item for item in captures if "#embedded@" in item.origin]
    assert len(embedded) >= _MIN_EMBEDDED_CAPTURES, (
        "the embedded grader scripts fell out of view; the file AST alone cannot see them"
    )
    git = git_captures(captures)
    assert len(git) >= _MIN_GIT_CAPTURES, (
        f"only {len(git)} text-mode git captures are visible; the floor is {_MIN_GIT_CAPTURES}, "
        "and 'nothing violates' is only reassuring while the rule can still see the domain"
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


_PORCELAIN = ["git", "worktree", "list", "--porcelain"]


def _git_repo(path: Path) -> Path:
    """An initialized repository at ``path``, for ``git worktree list``."""

    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], capture_output=True, check=True, timeout=120)
    return path


def _porcelain_bytes(repo: Path) -> bytes:
    """The bytes git wrote - the one reading no codec can disagree with."""

    return subprocess.run(_PORCELAIN, cwd=repo, capture_output=True, timeout=120, check=True).stdout


def _porcelain_text(repo: Path, encoding: str | None) -> str:
    """The same bytes through a reader, with ``encoding`` named or not named.

    The other keywords mirror ``WorktreeManager._run``, so two readings of one
    repository differ in exactly one thing: the codec the caller declared.
    """

    result = subprocess.run(
        _PORCELAIN,
        cwd=repo,
        capture_output=True,
        text=True,
        errors="replace",
        encoding=encoding,
        timeout=120,
        check=True,
    )
    return result.stdout


def _worktree_line(text: str) -> str:
    """The one path in a ``--porcelain`` listing."""

    lines = [line[len("worktree ") :] for line in text.splitlines() if line.startswith("worktree ")]
    assert len(lines) == 1, lines
    return lines[0]


def test_a_non_ascii_worktree_path_survives_the_reader(tmp_path: Path) -> None:
    """``worktree list`` must hand back the path git printed, not a locale guess.

    Measured on the cp936 machine that registered this batch: the path came back
    longer than it is, because git's UTF-8 bytes had been read with the machine code
    page - a wrong answer that no exception marks.  The gate used to demand that
    machine, through ``skipif(host locale is UTF-8)``, so on CI it reported nothing
    at all: not a pass, not a failure, just one test fewer than the file had.

    What is asserted now is the invariant the skip threw away, and it holds on every
    host: git's own bytes say what the path is, and production's answer has to equal
    those bytes read as UTF-8.  Deleting the ``encoding`` keyword reddens this gate
    only where the default codec differs from UTF-8; the structural git-capture rule
    is what catches it on both hosts.  So the coverage this gate owns alone is the
    class a keyword shape cannot see - right keyword, wrong answer - measured with
    that mutation (keep ``encoding="utf-8"``, return ``str(path)`` instead of
    ``path.as_posix()`` from ``_decorate``): this gate reddens on a cp936 host and on
    a UTF-8-mode one alike, and the structural rule stays green on both.
    """

    from minicc.worktree import WorktreeManager

    repo = _git_repo(tmp_path / _NON_ASCII_DIR)
    git_says = _worktree_line(_porcelain_bytes(repo).decode("utf-8"))
    entries = WorktreeManager(repo).list()
    assert len(entries) == 1, entries
    # Both sides go through the same path normalization ``_decorate`` applies, so the
    # only thing left for them to disagree about is the decoding.
    expected = Path(git_says).resolve().as_posix()
    returned = entries[0]["path"]
    assert returned == expected, (
        f"git wrote {expected!r} in UTF-8; production returned {returned!r}, and reading the "
        f"same bytes as {_ALIEN_READER_CODEC} gives "
        f"{_worktree_line(_porcelain_text(repo, _ALIEN_READER_CODEC))!r}"
    )


def test_the_alien_reader_is_the_one_that_disagrees(tmp_path: Path) -> None:
    """The fixture's non-vacuity, and the exact boundary of the gate above.

    Three readings of one byte string, all host-independent in what they prove:
      * UTF-8 gives the directory back, so the repository really is where the test
        put it;
      * ``_ALIEN_READER_CODEC`` gives something *else*, so the bytes are UTF-8-only -
        without this, a green "production agrees with UTF-8" could be an artifact of
        an ASCII-only path, which is how a codec gate quietly stops being one;
      * the unnamed reading is this host's own default.  Where it agrees with UTF-8,
        this gate cannot see a deleted pin at all - which is recorded as a boundary
        instead of hidden behind a skip, and is why the structural git-capture rule
        stays load-bearing.  Measured, the default is not taken from
        ``locale.getpreferredencoding`` at call time (patching it, or
        ``io.text_encoding``, changed the decoding on neither a cp936 host nor a
        UTF-8-mode one), so a test cannot manufacture the mismatch on demand.
    """

    repo = _git_repo(tmp_path / _NON_ASCII_DIR)
    utf8 = _worktree_line(_porcelain_text(repo, "utf-8"))
    alien = _worktree_line(_porcelain_text(repo, _ALIEN_READER_CODEC))
    default = _worktree_line(_porcelain_text(repo, None))
    assert utf8.endswith(_NON_ASCII_DIR), utf8
    assert alien != utf8, (
        f"reading git's bytes as {_ALIEN_READER_CODEC} returned them unchanged: the fixture has "
        "no non-ASCII bytes left, so every claim in this file about a wrong reader is vacuous"
    )
    print(
        "this host's default reader codec agrees with utf-8 (True means a deleted pin is "
        f"invisible to this gate): {default == utf8}"
    )


def _assert_failure(failures: list[str], needle: str) -> None:
    assert any(needle in item for item in failures), f"{needle!r} is not among {failures}"


def test_every_production_capture_names_its_reader_or_carries_a_checked_proof() -> None:
    """Reading a child in the machine locale is allowed only where it cannot matter.

    Three shipping captures take that exemption (``_VERDICT_NEUTRAL_CAPTURES``):
    two compare an ASCII marker, so a parent and child that both follow the locale
    agree wherever the machine is, and one never reads the stream at all.  Each of
    those reasons is re-derived from the AST on every run, not quoted from here.

    The domain gets a floor of its own because both lists below are empty on a
    clean tree: if ``production_captures`` went blind, the gate would report the
    suite's most compliant finding about an inventory it could no longer see.
    """

    scanned = scanned_captures()
    production = text_captures(production_captures(scanned))
    assert len(production) >= _MIN_PRODUCTION_TEXT_CAPTURES, (
        f"only {len(production)} production text-mode captures are visible; "
        f"the floor is {_MIN_PRODUCTION_TEXT_CAPTURES}"
    )
    offenders = [item.label() for item in unpinned_outside_the_table(scanned)]
    assert offenders == [], f"shipping code at the mercy of the machine locale: {offenders}"
    failures = exemption_failures(scanned)
    assert failures == [], f"exemptions that no longer hold: {failures}"


def test_an_exemption_is_a_claim_this_file_can_falsify() -> None:
    """Every shape of rot the table is exposed to, planted and caught.

    A witness per hole, because each one fails differently: a table that silently
    stops matching its call site would keep the offending capture exempt forever,
    a proof with no body is prose (see ``_code_only``), and a checker that only
    ever returns "holds" is the same gate with extra steps.
    """

    planted = _scan_source(_SYNTHETIC_PRODUCTION_UNPINNED, "minicc/planted.py")
    assert [item.label() for item in planted] == [_PLANTED], planted
    assert [item.label() for item in unpinned_outside_the_table(planted, table={})] == [
        _PLANTED
    ], "an unpinned shipping capture with no exemption must be an offender"
    assert unpinned_outside_the_table(planted, table={_PLANTED: []}) == [], (
        "the table is the escape hatch; if listing a call changes nothing, the "
        "offender list and the table are not the same mechanism"
    )
    assert exemption_failures(planted, table={_PLANTED: []}) == [
        f"{_PLANTED}: an exemption with no proof is a sentence"
    ]

    ascii_marker = {_PLANTED: ["ascii-marker:MINICC_PLANTED_COMPLETE"]}
    holds = _scan_source(_SYNTHETIC_PRODUCTION_ASCII_MARKER, "minicc/planted.py")
    assert exemption_failures(holds, table=ascii_marker) == [], "the compliant shape must not read as a violation"
    rotted = _scan_source(_SYNTHETIC_PRODUCTION_NON_ASCII_MARKER, "minicc/planted.py")
    _assert_failure(
        exemption_failures(rotted, table=ascii_marker),
        "travels beside non-ASCII text",
    )

    consumed = _scan_source(_SYNTHETIC_PRODUCTION_CONSUMED, "minicc/planted.py")
    _assert_failure(exemption_failures(consumed, table={_PLANTED: ["no-consumer:completed"]}), "is read")
    _assert_failure(
        exemption_failures(holds, table={_PLANTED: ["no-consumer:output"]}),
        "is not bound to",
    )
    _assert_failure(
        exemption_failures(holds, table={_PLANTED: ["nothing-of-this-shape:x"]}),
        "unknown proof shape",
    )
    stale = {_PLANTED.replace(":2 ", ":99 "): ["ascii-marker:MINICC_PLANTED_COMPLETE"]}
    _assert_failure(exemption_failures(holds, table=stale), "0 production text-mode captures")


def test_the_real_table_names_the_code_that_ships() -> None:
    """The table's own keys, spelled out where a reader can check one against git.

    ``exemption_failures`` proves each key still resolves and still holds; this
    pins the set, so a new exemption cannot arrive as an extra dictionary entry
    without also arriving here, where it has a line to be argued about.
    """

    assert sorted(_VERDICT_NEUTRAL_CAPTURES) == [
        "minicc/behavior_bench.py:105 subprocess.run",
        "minicc/bench_tasks.py:229 subprocess.run",
        "minicc/benchmarks.py:661 subprocess.run",
    ], sorted(_VERDICT_NEUTRAL_CAPTURES)
