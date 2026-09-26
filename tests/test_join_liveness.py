"""M8-T71: a join that takes a timeout must be followed by a liveness read.

``thread.join(timeout=5)`` returns whether or not the thread stopped.  Reading
the answer back is the only way a test can say "the server is down" or "that
worker is gone" - and until this batch, 15 of the 18 places in ``tests/`` that
join a thread never read it again.

M8-T68 made the HTTP fixtures prove the server thread was alive *before*
publishing its url.  The same reasoning applies at the other end and was missed
there: a fixture that reports a stopped-looking server it never verified as
stopped can keep answering on its socket, and the service behind it keeps
writing the shared task store, after the test that owns it has finished.  Five
of the 15 read ``is_alive()`` at startup and then never again, which is exactly
the shape this gate exists to catch: the claim was made about the beginning of
the window and never about the end.

Census, measured on this tree by the AST walk below (``tests/`` only, run
2026-09-26 against ``916a31c``):

  19 join calls on a resolved thread receiver, in 18 (function, receiver) pairs.
  Resolved means the receiver names something bound to ``threading.Thread(...)``:
  directly, as the element of a list/comprehension of them, or as ``self.thread``
  in a fixture class.  Counting joins by attribute name alone also counts
  ``", ".join(...)``, which is how an earlier pass at this census reported 49.
  All 19 are bounded (none is a bare ``join()``), and only 3 pairs read
  ``is_alive()`` at a line after their first join.  15 did not; this batch gives
  every one of them that read.

The rule is per (function, receiver), not per call: a test that joins once to
judge and again in ``finally`` to clean up makes one claim, not two.  And a
liveness read before the join is not a claim about the join - it is a claim
about startup.
"""

from __future__ import annotations

import ast
from pathlib import Path

JOIN_METHODS = {"join", "is_alive"}


def _thread_expr(node: ast.AST, bare_thread: bool) -> bool:
    """``threading.Thread(...)``, bare ``Thread(...)``, or a list of either."""
    if isinstance(node, ast.List):
        return any(_thread_expr(elt, bare_thread) for elt in node.elts)
    if isinstance(node, ast.ListComp):
        return _thread_expr(node.elt, bare_thread)
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr == "Thread":
        base = func.value
        while isinstance(base, ast.Attribute):
            base = base.value
        return isinstance(base, ast.Name) and base.id == "threading"
    return isinstance(func, ast.Name) and func.id == "Thread" and bare_thread


def thread_receivers(tree: ast.AST) -> set[str]:
    """Names in this module that hold a thread object."""
    bare_thread = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "threading"
        and any(alias.name == "Thread" for alias in node.names)
        for node in ast.walk(tree)
    )
    found: set[str] = set()
    lists: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.For)):
            continue
        value = node.value if isinstance(node, ast.Assign) else node.iter
        if not _thread_expr(value, bare_thread):
            continue
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if isinstance(value, (ast.List, ast.ListComp)):
                        lists.add(target.id)
                    else:
                        found.add(target.id)
            continue
        if isinstance(node.target, ast.Name):
            # `for t in [Thread(...), ...]` - the loop variable is a thread, and
            # that is where the join usually sits.
            found.add(node.target.id)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.For)
            and isinstance(node.iter, ast.Name)
            and node.iter.id in lists
            and isinstance(node.target, ast.Name)
        ):
            found.add(node.target.id)
    found.discard("")
    return found


def join_claims(source: str) -> list[dict[str, object]]:
    """One record per (function, thread receiver) pair that joins a thread."""
    tree = ast.parse(source)
    names = thread_receivers(tree)
    records: list[dict[str, object]] = []
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    for func in functions:
        by_receiver: dict[str, list[tuple[int, str, bool]]] = {}
        for node in ast.walk(func):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in JOIN_METHODS
            ):
                continue
            receiver = ast.get_source_segment(source, node.func.value)
            if receiver is None:
                continue
            if receiver not in names and receiver != "self.thread":
                continue
            bounded = True
            if node.func.attr == "join":
                bounded = bool(node.args) or any(k.arg == "timeout" for k in node.keywords)
            by_receiver.setdefault(receiver, []).append((node.lineno, node.func.attr, bounded))
        for receiver, events in by_receiver.items():
            joins = [event for event in events if event[1] == "join"]
            if not joins:
                continue
            first = min(lineno for lineno, _kind, _bounded in joins)
            records.append(
                {
                    "function": func.name,
                    "receiver": receiver,
                    "first_join": first,
                    "joins": len(joins),
                    "unbounded_joins": sorted(lineno for lineno, _k, bounded in joins if not bounded),
                    "claims": sorted(
                        lineno
                        for lineno, kind, _bounded in events
                        if kind == "is_alive" and lineno > first
                    ),
                }
            )
    return records


def labels(source: str) -> list[str]:
    """The join sites this source reports, claimed or not."""
    return [
        f"{record['function']}:{record['receiver']}@{record['first_join']}"
        for record in join_claims(source)
    ]


def unclaimed(source: str) -> list[str]:
    return [
        f"{record['function']}:{record['receiver']}@{record['first_join']}"
        for record in join_claims(source)
        if not record["claims"]
    ]


def line_of(source: str, needle: str) -> int:
    """The single line carrying `needle` - so the synthetic expectations below
    are derived from the fixtures instead of being retyped by hand."""
    hits = [index for index, text in enumerate(source.splitlines(), start=1) if needle in text]
    assert len(hits) == 1, f"{needle!r} found on {hits}, expected exactly one line"
    return hits[0]


CLEAN_JUDGE_THEN_CLEANUP = '''
import threading


def test_cancel():
    worker = threading.Thread(target=work)
    worker.start()
    try:
        worker.join(8)
        assert not worker.is_alive(), "the thread never stopped"
    finally:
        worker.join(8)
'''

CLEAN_FIXTURE_TEARDOWN = '''
class _Server:
    def start(self):
        self.thread = threading.Thread(target=serve)

    def shutdown(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        assert not self.thread.is_alive(), "the server thread is still listening"
'''

CLEAN_AFTER_A_LOOP = '''
def test_many():
    threads = [threading.Thread(target=work) for _ in range(4)]
    for t in threads:
        t.join(timeout=5)
    assert all(not t.is_alive() for t in threads), "a writer outlived its join"
'''

CLEAN_STARTUP_POLL_AND_JOIN_WITH_CLAIM = '''
def test_server():
    thread = threading.Thread(target=serve)
    thread.start()
    assert thread.is_alive(), "the server never started"
    request(thread)
    thread.join(timeout=5)
    assert not thread.is_alive(), "the server never stopped"
'''

DIRTY_NO_CLAIM = '''
def test_server():
    thread = threading.Thread(target=serve)
    thread.start()
    request(thread)
    thread.join(timeout=5)
'''

DIRTY_CLAIM_ONLY_BEFORE = '''
def test_server():
    thread = threading.Thread(target=serve)
    thread.start()
    assert thread.is_alive(), "the server never started"
    request(thread)
    thread.join(timeout=5)
'''

DIRTY_BARE_JOIN = '''
def test_server():
    thread = threading.Thread(target=serve)
    thread.start()
    request(thread)
    thread.join()
'''

NOT_A_THREAD_JOIN = '''
def test_message():
    problems = ["a", "b"]
    joined = ", ".join(problems)
    assert joined == "a, b"
'''


def test_the_scanner_answers_both_ways_on_synthetic_source() -> None:
    assert unclaimed(CLEAN_JUDGE_THEN_CLEANUP) == [], (
        "one claim after the first join covers a second, cleanup join of the same "
        "thread - counting per call would demand a redundant assert"
    )
    assert unclaimed(CLEAN_FIXTURE_TEARDOWN) == [], "a fixture teardown claim counts"
    assert unclaimed(CLEAN_AFTER_A_LOOP) == [], (
        "a claim over the same list of threads is a claim per thread - and it only "
        f"counts if the scanner resolved them: {labels(CLEAN_AFTER_A_LOOP)}"
    )
    assert len(join_claims(CLEAN_AFTER_A_LOOP)) == 1, (
        f"the loop variable was not resolved to a thread ({labels(CLEAN_AFTER_A_LOOP)}); "
        f"an empty report here would make the line above green by finding nothing"
    )
    assert unclaimed(CLEAN_STARTUP_POLL_AND_JOIN_WITH_CLAIM) == [], (
        "a startup liveness poll plus a post-join claim is the shape this gate wants"
    )

    join_line = line_of(DIRTY_NO_CLAIM, "thread.join(")
    assert unclaimed(DIRTY_NO_CLAIM) == [f"test_server:thread@{join_line}"], (
        "a bounded join with no liveness read after it must be reported"
    )
    assert unclaimed(DIRTY_CLAIM_ONLY_BEFORE) == [
        f"test_server:thread@{line_of(DIRTY_CLAIM_ONLY_BEFORE, 'thread.join(')}"
    ], "is_alive() before the join is a claim about startup, not about the stop"
    assert unclaimed(DIRTY_BARE_JOIN) == [
        f"test_server:thread@{line_of(DIRTY_BARE_JOIN, 'thread.join(')}"
    ], "an unbounded join is still a join nobody reads the result of"
    assert labels(NOT_A_THREAD_JOIN) == [], (
        '", ".join(...) is not a thread join - counting by attribute name alone '
        "invents violations in string helpers"
    )


def test_the_scanner_sees_whether_a_join_can_time_out() -> None:
    records = join_claims(DIRTY_BARE_JOIN)
    assert len(records) == 1, records
    bare = line_of(DIRTY_BARE_JOIN, "thread.join()")
    assert records[0]["unbounded_joins"] == [bare], (
        "join() and join(timeout=) fail differently - the first hangs the run, the "
        "second passes vacuously - so the record has to tell them apart"
    )
    bounded = join_claims(DIRTY_NO_CLAIM)
    assert bounded[0]["unbounded_joins"] == [], bounded


def test_every_thread_join_in_the_suite_is_followed_by_a_liveness_read() -> None:
    files = sorted(Path("tests").glob("*.py"))
    assert len(files) >= 70, (
        f"the gate scanned {len(files)} modules under tests/ - if the suite moved, "
        f"this test is green because it found nothing, not because it passed"
    )
    records: list[str] = []
    reported: list[str] = []
    for path in files:
        source = path.read_text(encoding="utf-8")
        for record in join_claims(source):
            records.append(f"{path}:{record['function']}:{record['receiver']}@{record['first_join']}")
            if not record["claims"]:
                reported.append(f"{path}:{record['function']}@join-line-{record['first_join']}")
    assert len(records) >= 15, (
        f"only {len(records)} thread joins were resolved across {len(files)} modules; "
        f"the receiver rule has stopped matching the real fixtures ({records})"
    )
    assert not reported, (
        f"{len(reported)} thread join(s) take a timeout and are never read back: "
        f"{reported}. join(timeout=N) returning does not mean the thread stopped - "
        "assert not thread.is_alive() after it, and name what a living thread can "
        "still do (answer on its socket, write the task store, hold tmp_path open)."
    )
