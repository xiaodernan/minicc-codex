"""M8-T70: a sleep that is not polling must name the fact it stands in for.

M8-T68 closed the HTTP half of one defect class - a fixture that published a
url before proving the server was alive and had answered.  This batch is the
same class in its plainest form: ``time.sleep(X)`` written where the test
actually needed "the other side has reached state Y".  A fixed beat cannot
prove Y; it can only be lucky about it, and on this repository it was lucky in a
way that let two callers claim to share one approval prompt while only one of
them was attached to it (measured: tests/test_permissions_approval.py).

Census, measured on this tree by the AST walk below (``tests/`` only, run
2026-09-26 against ``3f4f221``):

  61 lines mention ``time.sleep(``.  47 of them are real blocking calls; the
  other 14 put a sleep inside a string handed to a child process, where it *is*
  the behaviour under test, so no rule here applies to it.  A separate
  population, not part of either count: 4 ``asyncio.sleep`` calls, out of scope
  because a coroutine yielding is not a thread parking itself.
  Of the 47, 37 sit inside a loop that names a budget, so they poll, and 10 are
  flat - a beat in a straight line.  Each of those 10 was read:

    4 replaced by a bounded wait on the observable fact -
      tests/test_subagent_streaming.py (provider.turns, was sleep 0.5 before
      signalling cancel),
      tests/test_permissions_approval.py x2 (the approval_request frame, and
      the merged waiter count, both was sleep 0.1),
      tests/test_task_worker.py (the alive log growing, was sleep 1.0);
    6 remain, all declared in place, because none of them waits for a fact this
      test can poll - and one of them can only be checked afterwards:
      tests/test_core_tools.py (sleep 0.25 before cancelling a bash child; the
      child's first line is only visible once run_process returns, so the beat
      is now followed by a witness that it did start),
      tests/test_parallel_writes.py x2 (open the overlap window a concurrency
      counter measures - the sleep creates the state, it does not wait for it),
      tests/test_hooks.py and tests/test_verifier_lifecycle.py (outlive a
      declared 3s timeout so "no marker file" means something),
      tests/test_task_worker.py (the negative twin of the growth check: prove
      the orphan did stop ticking - an absence needs a window, not a poll).

After the batch the same walk measures 44 blocking sleeps in 79 modules: 38 poll,
6 are flat, and the gate reports none of them.  The arithmetic is visible rather
than assumed - four flat beats disappeared and one new polling sleep was written
in ``test_subagent_streaming.py``, so 47 - 4 + 1 = 44 and 10 - 4 = 6.  Run this
file against ``3f4f221``'s ``tests/`` and it names all ten sites verbatim; that
red is the thing this gate exists to make impossible.

The rule is deliberately about *declaration*, not about shape: deciding whether
a beat could be replaced by a poll needs a reader, and this batch is what that
reader produces.  What the gate can enforce is that a future author writes down
the fact they are assuming - the sentence that made four of these ten disappear.

M8-T198 moved two things that were hiding inside that arithmetic, both measured
on the live tree first.

* The census took its population from the *invocation* directory:
  ``Path("tests").glob("*.py")``.  Running this one file the way whoever is
  editing it runs it - ``cd tests``, ``pytest test_blind_wait.py`` - made the
  walk find nothing, and the gate red with 「expected the whole suite (79 when
  this landed), saw 0」.  Measured: 2 failed in 0.48s from ``tests/``, the same
  two nodeids 2 passed from the repository root.  The sentence reads as though
  the suite disappeared; what disappeared was only the directory the launcher
  stood in.  ``test_join_liveness.py`` had the identical line, and those two are
  the only places in the repository that walk ``tests/`` from the working
  directory (measured: 2 hits).
* The scanner recognised a blocking sleep by one spelling - a ``.sleep``
  attribute on the bare name ``time``.  Measured against the shipped scanner, an
  undeclared beat written through each of four ordinary bindings came back
  ``undeclared=[]``: ``import time as clock``, a function-local
  ``import time as time_mod``, ``from time import sleep``, and
  ``from time import sleep as nap``.  The alias form is not hypothetical:
  ``tests/test_bench_tasks.py:339`` imports ``time as time_mod`` and parks its
  reader on ``time_mod.sleep(0.001)`` at ``:354`` - a blocking sleep inside a
  file the census does read, and inside a call it never counted, so the
  denominator the docstring above presents as arithmetic (48 blocking sites
  today) was reading 49.

Provenance is now resolved per call from the bindings the scopes around it
actually carry, so the ``asyncio`` exclusion became a rule instead of the same
blindness that hid the alias: the census names the coroutine yields it saw and
refused, and it names every sleep-shaped call it could not attribute at all -
which used to be indistinguishable from "no sleep here".  A bare ``sleep(...)``
with no binding in sight is counted as blocking rather than exempted: an unknown
name must not become a way to park a thread without writing the claim down.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

MARKER = "# wait-claim:"

# A claim has to be a phrase, not a word or an empty colon: "# wait-claim: x"
# documents nothing, and the point is the sentence that says what is true by now.
MIN_CLAIM_LENGTH = 12

#: The modules a ``sleep`` call can arrive from, and what parking on it means.
#: ``asyncio`` is in this table so the census can *name* its exclusion, not
#: because a coroutine yield owes anybody a claim.
SLEEP_MODULES = {"time": "blocking", "asyncio": "coroutine"}

#: The suite this census reads: the directory this file lives in, never the
#: directory the launcher happened to stand in.
SUITE_DIR = Path(__file__).resolve().parent

#: Modules the census's own claims lean on.  Named rather than counted: the walk
#: needs these files, and an empty population satisfies any number floor - which
#: is the sentence the old floor carried as 「79 when this landed」.
CARRIER_MODULES = (
    "test_blind_wait.py",       # this file: the synthetic beats
    "test_bench_tasks.py",      # the shipped alias: time_mod.sleep at :354
    "test_core_tools.py",       # a declared flat beat
    "test_parallel_writes.py",  # two declared flat beats
)

#: The two gates that read the whole suite. Both must answer the same way from
#: any directory; the paths are absolute so the invocation directory cannot pick
#: a different tree.
CENSUS_GATES = (
    ("test_blind_wait.py", "test_every_flat_sleep_in_the_test_suite_declares_what_it_assumes"),
    ("test_join_liveness.py", "test_every_thread_join_in_the_suite_is_followed_by_a_liveness_read"),
)


def _parents(tree: ast.AST) -> dict[int, ast.AST]:
    out: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            out[id(child)] = node
    return out


def _own_nodes(scope: ast.AST):
    """Nodes of *scope* itself, stopping at each nested def/class body.

    A nested function binds its own names; answering a call in the parent scope
    from an import written inside a child would repeat, in the other direction,
    the mistake that hid the aliases.  The nested def's own node is still
    yielded, because defining ``sleep`` there is what shadows the binding.
    """
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        stack.extend(ast.iter_child_nodes(node))


def _bound_names(node: ast.AST) -> list[str]:
    """Every name one statement binds, for the "is this receiver something?" test."""
    names: list[str] = []
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        for alias in node.names:
            names.append(alias.asname or alias.name.split(".")[0])
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        names.append(node.name)
    elif isinstance(node, ast.Assign):
        names.extend(t.id for t in node.targets if isinstance(t, ast.Name))
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        names.append(node.target.id)
    elif isinstance(node, (ast.For, ast.AsyncFor)) and isinstance(node.target, ast.Name):
        names.append(node.target.id)
    elif isinstance(node, (ast.With, ast.AsyncWith)):
        for item in node.items:
            if isinstance(item.optional_vars, ast.Name):
                names.append(item.optional_vars.id)
    elif isinstance(node, ast.ExceptHandler) and node.name:
        names.append(node.name)
    elif isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
        names.append(node.target.id)
    elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
        for generator in node.generators:
            if isinstance(generator.target, ast.Name):
                names.append(generator.target.id)
    return names


def _parameters(fn: ast.AST) -> list[str]:
    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return []
    args = fn.args
    plain = list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
    return [a.arg for a in plain] + [a for a in (args.vararg, args.kwarg) if a]


def _scope_tables(tree: ast.AST) -> dict[int, dict[str, object]]:
    """Per scope: which receiver names are a sleep module, which call names are its
    ``sleep``, which names the scope defines, and which names it binds at all.

    Later statements win inside one scope, which is what Python does to a name
    that gets rebound; a scope that both imports and defines ``sleep`` is decided
    by whichever of the two is written last.
    """
    tables: dict[int, dict[str, object]] = {}
    for scope in ast.walk(tree):
        if not isinstance(scope, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        receivers: dict[str, str] = {}
        sleeps: dict[str, str] = {}
        defined: set[str] = set(_parameters(scope))
        bound: set[str] = set(_parameters(scope))
        for node in sorted(_own_nodes(scope), key=lambda n: getattr(n, "lineno", 0) or 0):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in SLEEP_MODULES:
                        receivers[alias.asname or alias.name] = alias.name
            elif isinstance(node, ast.ImportFrom) and node.module in SLEEP_MODULES:
                for alias in node.names:
                    if alias.name == "sleep":
                        sleeps[alias.asname or alias.name] = node.module
            # Anything that binds a name other than the two imports above takes
            # the name over: a scope that writes ``def sleep`` owns it, and the
            # census must read that call as a helper, not as the standard library.
            shadowing = not isinstance(node, (ast.Import, ast.ImportFrom))
            for name in _bound_names(node):
                bound.add(name)
                if shadowing:
                    defined.add(name)
                    receivers.pop(name, None)
                    sleeps.pop(name, None)
        tables[id(scope)] = {
            "receivers": receivers,
            "sleeps": sleeps,
            "defined": defined,
            "bound": bound,
        }
    return tables


def _enclosing_scopes(node: ast.AST, parents: dict[int, ast.AST]) -> list[ast.AST]:
    """Innermost scope first, ending at the module."""
    scopes: list[ast.AST] = []
    cursor = parents.get(id(node))
    while cursor is not None:
        if isinstance(cursor, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            scopes.append(cursor)
        cursor = parents.get(id(cursor))
    return scopes


def _callee_parts(call: ast.Call, sleeper_names: set[str]) -> tuple[str, str] | None:
    """(name the callee goes through, form) for a call that could be a sleep.

    ``form`` is ``attr`` for ``<name>.sleep(...)`` - including a chain, which is
    resolved by its root name, so ``self.clock.sleep(...)`` is read as a method on
    ``self`` - and ``bare`` for a call of a name this module binds to a ``sleep``.
    The bare filter is the module's own binding table plus the literal ``sleep``:
    without it every function call in the suite would be a candidate, and with
    only the literal it would miss ``from time import sleep as nap``.
    """
    if isinstance(call.func, ast.Attribute):
        if call.func.attr != "sleep":
            return None
        root = call.func.value
        while isinstance(root, ast.Attribute):
            root = root.value
        if not isinstance(root, ast.Name):
            return "unrooted", "unrooted"
        return root.id, "attr"
    if isinstance(call.func, ast.Name) and (call.func.id == "sleep" or call.func.id in sleeper_names):
        return call.func.id, "bare"
    return None


def _provenance(
    call: ast.Call,
    scopes: list[ast.AST],
    tables: dict[int, dict[str, object]],
    sleeper_names: set[str],
) -> tuple[str, bool]:
    """(provenance, attributed) for one sleep-shaped call.

    ``blocking`` is counted and owes a claim; ``coroutine`` and ``method`` are
    refused; ``local-helper`` is a function this file owns.  A bare ``sleep(...)``
    that nothing binds is ``blocking`` and unattributed - the census declines to
    turn "I could not work this out" into "no beat here".
    """
    parts = _callee_parts(call, sleeper_names)
    if parts is None:
        return "not-a-sleep", False
    name, form = parts
    if form == "unrooted":
        return "method", False
    for scope in scopes:
        table = tables[id(scope)]
        receivers = table["receivers"]
        sleeps = table["sleeps"]
        binding = (receivers if form == "attr" else sleeps).get(name)
        if isinstance(binding, str):
            return SLEEP_MODULES[binding], True
        if form == "bare" and name in table["defined"]:
            return "local-helper", True
        if form == "attr" and name in table["bound"]:
            return "method", True
    return ("blocking", False) if form == "bare" else ("method", False)


def sleep_records(source: str) -> list[dict]:
    """Every sleep-shaped call in a module: its line, provenance, and loop status.

    A sleep is *not* flat when any ``while``/``for`` between it and the nearest
    enclosing function (or the module) contains it - a polling loop is the shape
    this file wants, and it needs no declaration.  Sleeps written inside a string
    literal are the behaviour under test, not a wait, and have no call node to
    find.
    """
    tree = ast.parse(source)
    parents = _parents(tree)
    tables = _scope_tables(tree)
    sleeper_names = {name for table in tables.values() for name in table["sleeps"]}
    lines = source.splitlines()
    records: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _callee_parts(node, sleeper_names) is None:
            # Asked before the scope walk: every other call in the file would
            # otherwise pay for a parent chain it never uses.
            continue
        scopes = _enclosing_scopes(node, parents)
        provenance, attributed = _provenance(node, scopes, tables, sleeper_names)
        cursor = parents.get(id(node))
        in_loop = False
        while cursor is not None:
            if isinstance(cursor, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                break
            if isinstance(cursor, (ast.While, ast.For, ast.AsyncFor)):
                in_loop = True
                break
            cursor = parents.get(id(cursor))
        lineno = node.lineno
        own = lines[lineno - 1]
        # Any comment in the run directly above the call (blank lines allowed)
        # can carry the claim; the sleep's own trailing comment wins.
        above: list[str] = []
        for back in range(lineno - 2, -1, -1):
            text = lines[back].strip()
            if not text:
                continue
            if text.startswith("#"):
                above.append(text)
                continue
            break
        claim = None
        for line in [own, *above]:
            index = line.find(MARKER)
            if index != -1:
                claim = line[index + len(MARKER):].strip()
                break
        records.append(
            {
                "lineno": lineno,
                "provenance": provenance,
                "attributed": attributed,
                "in_loop": in_loop,
                "claim": claim,
                "text": own.strip(),
            }
        )
    return records


def flat_sleeps(source: str) -> list[tuple[int, str | None]]:
    """Every blocking sleep not inside a loop, with the claim it declares."""
    return [
        (record["lineno"], record["claim"])
        for record in sleep_records(source)
        if record["provenance"] == "blocking" and not record["in_loop"]
    ]


def coroutine_sleeps(source: str) -> list[int]:
    """Lines the census identified as coroutine yields and refused by name."""
    return [r["lineno"] for r in sleep_records(source) if r["provenance"] == "coroutine"]


def unattributed_sleeps(source: str) -> list[int]:
    """Sleep-shaped lines the census could not place, whether it counted them or not."""
    return [r["lineno"] for r in sleep_records(source) if not r["attributed"]]


def _undeclared_claim(claim: str | None) -> bool:
    """A claim counts only if it is a sentence, not a label.

    Owned here rather than written twice, because the census gate and the ``undeclared``
    view must disagree about nothing: a beat one exempts and the other reports is a
    gate whose red cannot be attributed.
    """
    return claim is None or len(claim) < MIN_CLAIM_LENGTH or " " not in claim


def undeclared(source: str) -> list[int]:
    """Line numbers of flat sleeps whose claim is missing or decorative."""
    return [lineno for lineno, claim in flat_sleeps(source) if _undeclared_claim(claim)]


def suite_modules() -> list[Path]:
    """The census's population: ``tests/`` as this file lives in it."""
    files = sorted(SUITE_DIR.glob("*.py"))
    outside = [str(path) for path in files if not path.is_relative_to(SUITE_DIR)]
    assert not outside, f"the walk left its own directory: {outside}"
    return files


def census_nodeids() -> list[str]:
    return [f"{SUITE_DIR / name}::{gate}" for name, gate in CENSUS_GATES]


CLEAN_LOOP = '''
import time


def wait_for_it():
    begun = time.monotonic()
    while time.monotonic() - begun < 5.0:
        time.sleep(0.01)
'''

CLEAN_DECLARED = '''
import time


def starts_a_beat():
    time.sleep(0.2)  # wait-claim: the child has printed its banner
'''

CLEAN_COMMENT_ABOVE = '''
import time


def starts_a_beat():
    # wait-claim: the reader thread has parked on the pipe
    time.sleep(0.2)
'''

DIRTY_PLAIN = '''
import time


def hope():
    time.sleep(0.1)
    cancel.set()
'''

DIRTY_EMPTY_CLAIM = '''
import time


def hope():
    time.sleep(0.1)  # wait-claim:
'''

DIRTY_ONE_WORD_CLAIM = '''
import time


def hope():
    time.sleep(0.1)  # wait-claim: later
'''

DIRTY_INSIDE_STRING_ONLY = '''
import time


def spawn():
    source = "import time\\ntime.sleep(30)\\n"
    subprocess.Popen([sys.executable, "-c", source])
'''

#: The same beat, reached through four bindings.  Measured against the scanner
#: this batch replaced: every one of them came back invisible, and the
#: function-local alias is written in this suite today
#: (``test_bench_tasks.py:339``, its sleep at ``:354``).
ALIAS_SHAPES = {
    "module alias": (
        'import time as clock\n\n\ndef hope():\n    clock.sleep(0.1)\n',
        "clock.sleep(0.1)",
    ),
    "function-local alias": (
        'def hope():\n    import time as time_mod\n    time_mod.sleep(0.1)\n',
        "time_mod.sleep(0.1)",
    ),
    "from-import of the function": (
        'from time import sleep\n\n\ndef hope():\n    sleep(0.2)\n',
        "sleep(0.2)",
    ),
    "from-import with a rename": (
        'from time import sleep as nap\n\n\ndef hope():\n    nap(0.2)\n',
        "nap(0.2)",
    ),
}


def test_the_scanner_answers_both_ways_on_synthetic_source() -> None:
    for name, source in (
        ("loop poll needs no claim", CLEAN_LOOP),
        ("inline claim", CLEAN_DECLARED),
        ("claim on the line above", CLEAN_COMMENT_ABOVE),
        # a sleep that exists only inside a child's source string is not code
        ("string payload", DIRTY_INSIDE_STRING_ONLY),
    ):
        assert undeclared(source) == [], name

    for name, source in (
        ("bare beat", DIRTY_PLAIN),
        ("decorative claim", DIRTY_EMPTY_CLAIM),
        ("one-word claim", DIRTY_ONE_WORD_CLAIM),
    ):
        flagged = undeclared(source)
        assert len(flagged) == 1, f"{name}: expected one flat sleep, got {flagged}"

    # The loop exemption must not be a name match: a sleep in a nested helper
    # called from a loop is still flat, and a test that only polls in *some*
    # function must still declare the beats in the others.
    mixed = CLEAN_LOOP + '''

def beats():
    time.sleep(0.3)
'''
    flagged = undeclared(mixed)
    assert len(flagged) == 1, f"the beat in the other function must still be flat: {flagged}"
    assert "time.sleep(0.3)" in mixed.splitlines()[flagged[0] - 1], flagged
    declared = mixed.replace("time.sleep(0.3)", 'time.sleep(0.3)  # wait-claim: the worker is parked')
    assert undeclared(declared) == []


def test_a_sleep_reached_through_a_binding_is_still_a_blocking_sleep() -> None:
    """The four ways ``time.sleep`` reaches a call site, each asked for its line.

    Per shape, because dropping the receiver table, the from-import table, or the
    function-local scope each loses a different one - and the scanner this batch
    replaced lost all four.  The expected line is written per shape too: a renamed
    from-import is ``nap(0.2)``, and a check for the substring "sleep(" would be
    satisfied by any other line in the file while the real beat stayed unseen.
    """
    for name, (source, call_text) in ALIAS_SHAPES.items():
        flagged = undeclared(source)
        assert len(flagged) == 1, f"{name}: expected the alias beat to be counted, got {flagged}"
        line = source.splitlines()[flagged[0] - 1].strip()
        assert line == call_text, f"{name}: flagged the wrong line {line!r}, wanted {call_text!r}"
        records = sleep_records(source)
        assert len(records) == 1 and records[0]["attributed"], (
            f"{name}: counted but not attributed - {records}"
        )
        declared = source.replace("(0.1)", '(0.1)  # wait-claim: the reader is parked').replace(
            "(0.2)", '(0.2)  # wait-claim: the reader is parked'
        )
        assert undeclared(declared) == [], name

    # The mechanism has to reach a shipped file, or it is only ever tried on
    # strings written next to it.  Measured 2026-10-11: exactly one blocking
    # sleep reached through a binding other than the plain module name -
    # test_bench_tasks.py:354, inside a poll, so it is exempt from the rule and
    # inside the denominator all the same.
    aliased = [
        f"{path.name}:{record['lineno']} {record['text']}"
        for path in suite_modules()
        for record in sleep_records(path.read_text(encoding="utf-8"))
        if record["provenance"] == "blocking"
        and record["attributed"]
        and not record["text"].startswith("time.sleep(")
    ]
    assert aliased, (
        "the census no longer sees any blocking sleep reached through a binding other than the plain "
        "module name (measured 2026-10-11: test_bench_tasks.py:354, time_mod.sleep(0.001)). Either that "
        "alias became a plain call, in which case say what the receiver table is for now, or resolution "
        "stopped attributing it and the beat is invisible again"
    )


def test_a_coroutine_yield_is_excluded_by_name_not_by_blindness() -> None:
    """``asyncio.sleep`` is out of scope, and the census has to be able to say so.

    Before this batch the exclusion and the blindness produced the same output,
    so nothing could tell them apart: an over-broad fix that counted awaits as
    blocking, and the old scan that saw no sleep at all, both read as an empty
    report.  Both spellings are asked, because the from-import is the one the
    provenance walk has to refuse by name.
    """
    module_form = 'import asyncio\n\n\nasync def hope():\n    await asyncio.sleep(0.2)\n'
    from_form = 'from asyncio import sleep\n\n\nasync def hope():\n    await sleep(0.2)\n'
    await_line = module_form.splitlines().index("    await asyncio.sleep(0.2)") + 1
    for name, source in (("asyncio.sleep", module_form), ("from asyncio import sleep", from_form)):
        assert undeclared(source) == [], f"{name}: a coroutine yield is not a thread parking"
        assert flat_sleeps(source) == [], f"{name}: {flat_sleeps(source)}"
        assert coroutine_sleeps(source) == [await_line], (
            f"{name}: the census must name the line it refused: {coroutine_sleeps(source)}"
        )

    beside = module_form + "\ndef beats():\n    import time\n\n    time.sleep(0.1)\n"
    beat_line = beside.splitlines().index("    time.sleep(0.1)") + 1
    assert undeclared(beside) == [beat_line], (
        f"a blocking beat next to an excluded yield must still be flagged: {sleep_records(beside)}"
    )
    assert coroutine_sleeps(beside) == [await_line]


def test_a_helper_named_sleep_in_the_same_scope_is_not_the_standard_library() -> None:
    """A local ``def sleep`` answers to its own file, not to this census.

    The mirror of the case below: a bare ``sleep(...)`` that nothing binds is
    counted, one that the scope defines is not.  Getting that backwards invents
    violations in every test with a helper - which is how an earlier pass at the
    join census reported 49 joins instead of 21.
    """
    helper = 'def sleep(seconds):\n    return seconds\n\n\ndef hope():\n    sleep(0.1)\n'
    assert undeclared(helper) == [], sleep_records(helper)
    assert coroutine_sleeps(helper) == []
    assert unattributed_sleeps(helper) == [], (
        f"the census knows what this name is, so it must not report it as unplaced: {sleep_records(helper)}"
    )

    shadowed = (
        "from time import sleep\n"
        "\n"
        "\n"
        "def hope():\n"
        "    def sleep(seconds):\n"
        "        return seconds\n"
        "\n"
        "    sleep(0.1)\n"
    )
    assert undeclared(shadowed) == [], (
        f"a module-level import must not answer for a call the function shadows: {sleep_records(shadowed)}"
    )


def test_a_sleep_the_census_cannot_place_is_named_not_silently_skipped() -> None:
    """Both ways an attribution can fail, and the two different verdicts.

    An unbound bare ``sleep(...)`` parks a thread and owes the claim: the census
    counts it and says it could not place it.  A method on an object the file
    binds is not a module sleep: the census does not count it, and still says it
    did not place the name - so neither shape can become a quiet exemption.
    """
    bare = "def hope():\n    sleep(0.1)\n"
    assert unattributed_sleeps(bare) == [2], sleep_records(bare)
    assert undeclared(bare) == [2], "an unplaced beat must owe the same claim as a placed one"

    object_form = (
        "class Clock:\n"
        "    def sleep(self, seconds):\n"
        "        return seconds\n"
        "\n"
        "\n"
        "def hope(clock):\n"
        "    clock.sleep(0.1)\n"
    )
    assert undeclared(object_form) == [], (
        f"a method on a parameter is not the standard library parking a thread: {sleep_records(object_form)}"
    )
    assert unattributed_sleeps(object_form) == [], (
        f"the receiver here is bound by the file, so the census has placed it as a method: {sleep_records(object_form)}"
    )

    dotted = "def hope(clock):\n    clock().sleep(0.1)\n"
    assert undeclared(dotted) == []
    assert unattributed_sleeps(dotted) == [2], (
        f"a receiver that is not a name has to be said out loud, not skipped: {sleep_records(dotted)}"
    )


def test_the_census_reads_the_suite_from_this_file_s_own_directory() -> None:
    """The population is derived from where this file lives, not from the launcher.

    Named carriers rather than a count floor: the claims this gate makes need
    these particular files, and an empty walk satisfies any number.
    """
    files = suite_modules()
    names = {path.name for path in files}
    assert SUITE_DIR.name == "tests", f"the census directory is {SUITE_DIR}, not the suite this file is in"
    for carrier in CARRIER_MODULES:
        assert carrier in names, f"{carrier} is not in the census population ({len(files)} modules read)"
    assert len(files) >= len(CARRIER_MODULES), files

    # And no part of this file reaches for a path out of the working directory.
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    relative = [
        f"line {node.lineno}: Path({ast.literal_eval(node.args[0])!r})"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Path"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
        and not Path(node.args[0].value).is_absolute()
    ]
    assert not relative, f"this file builds a path out of the invocation directory again: {relative}"


def test_both_census_gates_answer_the_same_from_any_directory() -> None:
    """The defect as whoever runs it meets it: one file, from inside ``tests/``.

    Measured against the gates this batch replaced: from ``tests/`` they answered
    「expected the whole suite (79 when this landed), saw 0」 and 「the gate
    scanned 0 modules under tests/」 - 2 failed in 0.48s - while the same two
    nodeids from the repository root passed in 9.98s.  Nothing about the suite
    changed between those two runs; only the launcher's directory did.
    """
    for cwd in (SUITE_DIR, SUITE_DIR.parent):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", *census_nodeids(), "-q", "--no-header", "-p", "no:cacheprovider"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        )
        assert result.returncode == 0, (
            f"the census reads {len(suite_modules())} modules from this file's own directory, but the "
            f"same gates invoked from {cwd} exited {result.returncode}:\n{result.stdout[-2500:]}"
        )
        assert "2 passed" in result.stdout, f"from {cwd}: {result.stdout[-900:]}"


def test_no_census_in_the_suite_resolves_its_population_from_the_working_directory() -> None:
    """The twin rule, over the whole suite: derive the tree you claim to cover.

    Both halves are asserted, because the interesting claim is the pair - no
    module may build a relative ``tests`` path, and the walk that replaces them
    has to be seen reaching ``__file__`` twice.  A scan matching nothing would
    report a clean suite for the wrong reason.
    """
    offenders: list[str] = []
    derived: list[str] = []
    for path in suite_modules():
        text = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(text)):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "Path"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and Path(node.args[0].value).parts[:1] == ("tests",)
            ):
                offenders.append(f"{path.name}:{node.lineno} Path({node.args[0].value!r})")
        if "__file__" in text and ".glob(" in text:
            derived.append(path.name)
    assert not offenders, (
        f"these lines take a suite population from the invocation directory: {offenders}. The census "
        "then measures wherever the launcher stood - and when that directory has no tests/, an empty "
        "result is reported as though the suite went missing, which is what happened here until this batch"
    )
    assert len(derived) >= 2, (
        f"only {derived} modules walk a suite from their own file; the census above has stopped reading "
        "anything, and its green is about nothing"
    )


def test_every_flat_sleep_in_the_test_suite_declares_what_it_assumes() -> None:
    files = suite_modules()
    # The population is named, not counted: 79 modules when this gate landed, 161
    # today, and an empty walk would satisfy any floor of that kind.
    names = {path.name for path in files}
    missing = set(CARRIER_MODULES) - names
    assert not missing, f"the census is not reading the suite it claims; missing {sorted(missing)} of {len(files)} modules"

    flat: list[str] = []
    reported: list[str] = []
    polling = 0
    refused: list[str] = []
    unplaced: list[str] = []
    for path in files:
        source = path.read_text(encoding="utf-8")
        # One parse per module: the census gate, the flat view and the declared view
        # all read the same records, so a file is not walked three times to say the
        # same thing about it.
        records = sleep_records(source)
        for record in records:
            where = f"{path.name}:{record['lineno']} {record['text']}"
            if record["provenance"] == "coroutine":
                refused.append(where)
            elif record["provenance"] == "blocking":
                polling += record["in_loop"]
                if not record["in_loop"]:
                    flat.append(f"{path.name}:{record['lineno']}")
                    if _undeclared_claim(record["claim"]):
                        reported.append(f"{path.name}:{record['lineno']}")
            if not record["attributed"]:
                unplaced.append(where)

    assert not reported, (
        f"{len(reported)} flat blocking sleep(s) wait on an undeclared assumption: "
        f"{reported}. Either replace the beat with a bounded wait on the fact "
        f"(see _wait_for / _wait_until in these files), or write on the line what "
        f"is true by the time it wakes - and if you can name that fact, you can "
        f"usually poll for it. (This run read {len(flat) + polling} blocking sleeps: "
        f"{len(flat)} flat, {polling} inside a loop, and {len(refused)} coroutine yields excluded.)"
    )
    # The gate is only as good as its reach; a scanner that found nothing would
    # pass the assertion above for the wrong reason.
    assert len(flat) >= 5, f"expected the declared beats to still be here, saw {flat}"
    assert not unplaced, (
        f"{len(unplaced)} sleep-shaped call(s) were read without a resolved binding: {unplaced}. Either "
        "the provenance walk cannot follow a shape this suite uses - then teach it, do not exempt the "
        "line - or a beat is parked under a name this census has never seen"
    )
