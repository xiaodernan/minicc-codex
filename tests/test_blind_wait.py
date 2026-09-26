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
"""

from __future__ import annotations

import ast
from pathlib import Path

MARKER = "# wait-claim:"

# A claim has to be a phrase, not a word or an empty colon: "# wait-claim: x"
# documents nothing, and the point is the sentence that says what is true by now.
MIN_CLAIM_LENGTH = 12


def _parents(tree: ast.AST) -> dict[int, ast.AST]:
    out: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            out[id(child)] = node
    return out


def flat_sleeps(source: str) -> list[tuple[int, str | None]]:
    """Every ``time.sleep()`` not inside a loop, with the claim it declares.

    A sleep is *not* flat when any ``while``/``for`` between it and the nearest
    enclosing function (or the module) contains it - a polling loop is the shape
    this file wants, and it needs no declaration.  Sleeps written inside a
    string literal are the behaviour under test, not a wait, and have no call
    node to find.
    """
    tree = ast.parse(source)
    parents = _parents(tree)
    lines = source.splitlines()
    found: list[tuple[int, str | None]] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "sleep"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "time"
        ):
            continue
        cursor = parents.get(id(node))
        in_loop = False
        while cursor is not None:
            if isinstance(cursor, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                break
            if isinstance(cursor, (ast.While, ast.For, ast.AsyncFor)):
                in_loop = True
                break
            cursor = parents.get(id(cursor))
        if in_loop:
            continue
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
        found.append((lineno, claim))
    return found


def undeclared(source: str) -> list[int]:
    """Line numbers of flat sleeps whose claim is missing or decorative."""
    bad: list[int] = []
    for lineno, claim in flat_sleeps(source):
        if claim is None or len(claim) < MIN_CLAIM_LENGTH or " " not in claim:
            bad.append(lineno)
    return bad


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


def test_every_flat_sleep_in_the_test_suite_declares_what_it_assumes() -> None:
    files = sorted(Path("tests").glob("*.py"))
    # 79 test modules in tests/ when this gate landed; a scanner that reached a
    # handful of them would pass the rule below for the wrong reason.
    assert len(files) >= 70, f"expected the whole suite (79 when this landed), saw {len(files)}"

    flat: list[str] = []
    reported: list[str] = []
    for path in files:
        source = path.read_text(encoding="utf-8")
        for lineno, _claim in flat_sleeps(source):
            flat.append(f"{path}:{lineno}")
        for lineno in undeclared(source):
            reported.append(f"{path}:{lineno}")

    assert not reported, (
        f"{len(reported)} flat time.sleep call(s) wait on an undeclared assumption: "
        f"{reported}. Either replace the beat with a bounded wait on the fact "
        f"(see _wait_for / _wait_until in these files), or write on the line what "
        f"is true by the time it wakes - and if you can name that fact, you can "
        f"usually poll for it."
    )
    # The gate is only as good as its reach; a scanner that found nothing would
    # pass the assertion above for the wrong reason.
    assert len(flat) >= 5, f"expected the declared beats to still be here, saw {flat}"
