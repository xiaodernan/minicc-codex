"""Narrow repair scope to evidence that can affect a failed verifier."""

from __future__ import annotations

import re
from typing import Any

#: M8-T291: tokens that say nothing about the code under test.  Two kinds
#: show up in a failed test's own name: the words that mark it as a test
#: (``test``, ``tests``, ``testing``) and the words that mark it as
#: *infrastructure* rather than subject (``src``, ``lib``, ``unit``,
#: ``spec``, ``specs``, ``case``, ``cases``).  A token like ``src`` would
#: otherwise match every file under ``src/`` - which is the opposite of
#: narrowing the scope.
#:
#: (``py`` is not here: the token filter drops anything shorter than three
#: characters, so a two-character fragment can never reach the set.)
_GENERIC_TEST_TOKENS = frozenset({
    "test", "tests", "testing",
    "src", "lib",
    "unit", "spec", "specs", "case", "cases",
})


def _token_match_score(path: str, tokens: set[str]) -> int:
    """How well a path matches the failed test's tokens.

    M8-T308: the match used to be a bare substring, and the scope kept
    the **last** twelve matches.  So a path that merely *contains* a
    token (``src/summary.py`` for the token ``sum``) counted exactly as
    much as the module the test actually imports, and enough of those
    pushed the real target out of the cut - which is the opposite of
    what this function exists for.

    Two strengths:

    * ``2`` - a whole path segment (or the file's stem) **is** the token;
    * ``1`` - the token appears inside a segment.
    """
    if not tokens:
        return 0
    segments = path.casefold().replace("\\", "/").split("/")
    stems = {segment.rsplit(".", 1)[0] for segment in segments}
    if any(token in stems for token in tokens):
        return 2
    if any(token in segment for segment in segments for token in tokens):
        return 1
    return 0


def repair_scope(events: list[dict[str, Any]], verification: dict[str, Any]) -> dict[str, object]:
    """Return bounded affected files and failed tests without guessing ownership.

    The agent still re-checks the files before editing.  This scope only prevents
    a verifier failure from causing an unfocused full-workspace repair prompt.

    M8-T314: a bash write names no path, so the scope was built from the
    events' ``path`` field alone and came out empty for a task that edited
    through the shell.  The loop's ``verification_required`` trace carries
    the paths it worked out, so those are read too.
    """
    writes: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("write") and event.get("path"):
            writes.append(str(event["path"]))
        detail = event.get("detail")
        if isinstance(detail, dict):
            for path in detail.get("changed_paths") or []:
                text = str(path or "").strip()
                if text:
                    writes.append(text)
    failed_tests = [str(item) for item in verification.get("failed_tests") or [] if str(item)]
    # M8-T308: only the **file** part of a failed test id names a module.
    # The function name describes the behaviour (``test_sum``), and its
    # fragments matched unrelated files (``src/summary.py``,
    # ``src/consume.py``) - which then crowded the real target out of the
    # cut.
    tokens = {
        fragment.casefold()
        for test in failed_tests
        for token in re.findall(r"[A-Za-z_][\w.-]{2,}", test.split("::", 1)[0])
        for fragment in re.split(r"[_.-]+", token)
        if len(fragment) >= 3
    }
    # M8-T291: the tokens that come from the test file's **own** name and
    # directory (``test``, ``tests``, ``py``) say nothing about the code
    # under test, and the match is a bare substring - so ``attestation.py``,
    # ``latest/parser.py`` and ``protester.md`` all "matched" a failed
    # ``tests/test_ledger.py``.  The real target was pushed out by the
    # false hits, and the reason always read "matched_failed_test".
    #
    # M8-T300: the match is still against the **whole path**, because the
    # token often names a *directory* (``tests/test_ledger.py`` refers to
    # ``src/ledger/service.py``).  Narrowing it to the file's stem threw
    # the real target away and left the scope with nothing to say - which
    # is exactly what this function exists to prevent.
    tokens -= _GENERIC_TEST_TOKENS
    # M8-T308: the matches are ordered by **strength**, so the cut that
    # keeps the last twelve keeps the *best* twelve.  The sort is stable,
    # so among equally strong matches the more recent write still wins.
    scored = sorted(
        ((path, _token_match_score(path, tokens)) for path in writes),
        key=lambda item: item[1],
    )
    related = [path for path, score in scored if score]
    targets = list(dict.fromkeys(related or writes))[-12:]
    return {
        "failed_tests": failed_tests[:12],
        "changed_paths": list(dict.fromkeys(writes))[-24:],
        "repair_targets": targets,
        "reason": "matched_failed_test" if related else "changed_file_evidence",
    }


__all__ = ["repair_scope"]
