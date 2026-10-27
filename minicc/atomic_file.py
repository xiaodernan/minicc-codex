"""Riding out the Windows sharing violation — one answer for the whole repository.

On Windows a destination that another handle still has open makes
``os.replace`` fail with ``PermissionError`` (WinError 5) for as long as that
handle is open: microseconds for a reader that is mid-``read_text``, longer for
a writer that is mid-swap.  The same window makes a plain ``read_text`` raise.
Both answers are wrong.  The file on disk is always *one complete version* —
either the old one or the new one — so "the operation was refused for a
moment" is not a reason to report "the file is empty", nor "the write did not
happen".

Three call sites had three different answers to that question:

* ``minicc/session.py`` rode it out with a flat 24 x 50ms retry on both the
  write side and the read side;
* ``minicc/webauth.py`` rode it out with 8 attempts on a growing backoff, and
  separately on the read side;
* ``minicc/workspaces.py`` had **no** answer at all: one refused swap dropped
  the write with a warning, and one refused read emptied the catalog.

This module is the one answer.  The budgets stay with the call sites, because
they are not the same decision — a session checkpoint is worth waiting longer
for than a "recently opened folders" list — but the *shape* of the answer
(ride it out, then fail the way the caller already expects to fail) lives here,
once.

Both helpers are idempotent by construction: a retry of ``os.replace`` re-uses
the same staging file, and a retry of ``read_text`` re-reads the same path.
Neither one can leave half a file behind.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable

#: A flat delay between attempts, or a callable that returns one per attempt.
#: The callable form exists because the token store wants a *growing* backoff
#: while the session checkpoint wants a flat one, and both are the same answer.
Delay = float | Callable[[int], float]

#: Default budget: 24 attempts x 50ms, the session checkpoint's number.
DEFAULT_ATTEMPTS = 24
DEFAULT_DELAY = 0.05


def _wait(delay: Delay, attempt: int) -> float:
    """How long to sleep before attempt ``attempt + 1``."""
    return delay(attempt) if callable(delay) else delay


def replace_with_retry(
    source: Path,
    target: Path,
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    delay: Delay = DEFAULT_DELAY,
) -> None:
    """``os.replace`` that rides out a transient sharing violation.

    Raises the last ``PermissionError`` once the budget is spent — the caller
    decides what a refused swap means, and every caller in this repository
    already has an answer for that.
    """
    for attempt in range(attempts):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(_wait(delay, attempt))


def read_text_with_retry(
    path: Path,
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    delay: Delay = DEFAULT_DELAY,
) -> str:
    """``path.read_text`` that rides out a transient sharing violation.

    Raises the last ``PermissionError`` once the budget is spent.
    """
    for attempt in range(attempts):
        try:
            return path.read_text(encoding="utf-8")
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(_wait(delay, attempt))


__all__ = ["read_text_with_retry", "replace_with_retry"]
