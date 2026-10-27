"""The cross-process sidecar lock — one answer for the whole repository.

A read-modify-write of a file that **several minicc processes share** is only
a transaction if the neighbours are excluded while it happens.  ``threading``
locks do not exclude a second *process*: they speak to this process and to
nobody else, so two processes that both succeed still drop each other's
entries.

The repository wrote this mechanism twice, with two different fates for a
refusal:

* ``minicc/session.py`` takes one byte of a ``<file>.lock`` sidecar across the
  checkpoint's write, and **raises** when the neighbour will not let go — a
  session checkpoint may not degrade into an unlocked write;
* ``minicc/workspaces.py`` takes the same byte of the same naming rule and
  **degrades** to an unlocked write with a warning — losing a recent-folder
  entry is cosmetic, refusing to start a second web server over one is not;
* ``minicc/tools/memory.py`` needs a third answer: a memory the model was
  told it had stored cannot be dropped silently, so a refusal is reported and
  the write is refused.

Two copies of one mechanism is how a fix stops being a fix: the second copy
gets its own constants, its own defaults, its own idea of what a refusal
means, and a reader cannot tell which one a file is protected by.  This module
is the one mechanism.  The **policy** on a refusal stays with the call site,
because a session checkpoint and a "recently opened folders" list are not the
same decision — the same way ``minicc/atomic_file.py`` keeps the *shape* of the
answer there and leaves the budget to the caller.

What the mechanism guarantees, and what it does not:

* It takes **one byte** of a sidecar named after the file it protects, using the
  non-blocking Windows mode (``msvcrt.LK_NBLCK``).  The blocking mode
  (``msvcrt.LK_LOCK``) parks the caller inside the C runtime for about ten
  seconds before it admits defeat, so a loop built on it charges seconds it
  never budgeted; the immediate mode answers in 0.000s and the retry loop owns
  the waiting.  On POSIX the same question is ``flock(LOCK_EX | LOCK_NB)``.
* It excludes a second handle **inside the same process** as well — which is
  what makes the exclusion real for a reader that asks the operating system
  "is the byte free right now?".
* It is **advisory**: it keeps cooperating minicc processes out of each other's
  read-modify-write and does nothing at all against a process that ignores it.
* On a machine with neither primitive it runs the body **unlocked** rather
  than failing: there is no lock to wait for, and refusing to write because the
  platform has no lock is not a decision this module gets to make.  The outcome
  says so (``supported=False``) so a caller can tell that apart from a
  neighbour that refused — and the sidecar is **not created** in that case,
  because a file left behind that claims to protect something is worse than
  no file.
* It never raises.  A refusal is **reported to the caller** (the yielded
  :class:`LockOutcome`), because only the caller knows what a refused lock
  means for the file it protects.

The primitives are **injectable** (``LockPrimitives``) and the call site
supplies them.  That is not decoration: the repository's own gates ask the
operating system questions about *this* module's lock by rebinding *this*
module's ``msvcrt`` / ``fcntl`` / ``time``, and a shared home that hard-coded
its own primitives would make those gates measure a copy of the code rather
than the code.
"""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Iterator

try:  # Windows
    import msvcrt
except ImportError:  # pragma: no cover - non-Windows
    msvcrt = None  # type: ignore[assignment]

try:  # POSIX
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

#: The naming rule: the sidecar is named after the file it protects.
LOCK_SUFFIX = ".lock"

#: One byte is enough.  The byte is a token, not a range.
LOCK_BYTES = 1

#: The default budget: 40 attempts x 50ms, the catalog's number.  Call sites
#: that want a different ceiling pass their own; the mechanism only owns the
#: shape of the wait.
DEFAULT_ATTEMPTS = 40
DEFAULT_DELAY = 0.05


def sidecar_path_for(target: Path) -> Path:
    """The sidecar that protects ``target`` — named after it."""
    return target.with_name(target.name + LOCK_SUFFIX)


@dataclass(frozen=True)
class LockPrimitives:
    """The three modules the mechanism asks.

    Injectable so that a caller (and the gates that watch it) can substitute
    them: rebinding ``msvcrt`` / ``fcntl`` / ``time`` on the **calling**
    module is how the repository's own lock gates ask the operating system
    questions about the shipped code.
    """

    msvcrt: Any = msvcrt
    fcntl: Any = fcntl
    time: Any = time


@dataclass(frozen=True)
class LockOutcome:
    """What the attempt to take the sidecar actually achieved.

    ``held`` is the only thing a caller may act on.  ``refusal`` carries the
    operating system's own reason when the byte was not ours, so the caller can
    name it instead of inventing one.  ``supported`` is False when this
    machine has no lock primitive at all — a different situation from a
    neighbour that refused, and a caller may treat them differently.
    """

    held: bool
    refusal: OSError | None = None
    attempts: int = 0
    delay: float = DEFAULT_DELAY
    supported: bool = True

    @property
    def ceiling(self) -> float:
        """The seconds this outcome's budget could have spent."""
        return self.attempts * self.delay


def _take_one_byte(handle: IO[str], primitives: LockPrimitives) -> None:
    """Take one byte of an open sidecar without waiting.

    Raises ``OSError`` when the byte belongs to somebody else.  The mode
    matters: the blocking one parks the caller inside the C runtime, so the
    retry loop's ceiling becomes a fiction.
    """
    handle.seek(0)
    if primitives.msvcrt is not None:
        primitives.msvcrt.locking(handle.fileno(), primitives.msvcrt.LK_NBLCK, LOCK_BYTES)
    elif primitives.fcntl is not None:
        primitives.fcntl.flock(handle.fileno(), primitives.fcntl.LOCK_EX | primitives.fcntl.LOCK_NB)
    else:  # pragma: no cover - no supported platform reaches this
        raise OSError("本机没有可用的跨进程锁原语（msvcrt 与 fcntl 均未导出）")


def _drop_one_byte(handle: IO[str], primitives: LockPrimitives) -> None:
    """Put the byte back; closing the handle is what guarantees the drop anyway."""
    handle.seek(0)
    if primitives.msvcrt is not None:
        primitives.msvcrt.locking(handle.fileno(), primitives.msvcrt.LK_UNLCK, LOCK_BYTES)
    elif primitives.fcntl is not None:
        primitives.fcntl.flock(handle.fileno(), primitives.fcntl.LOCK_UN)


def _acquire(
    lock_path: Path,
    *,
    attempts: int,
    delay: float,
    primitives: LockPrimitives,
) -> tuple[IO[str] | None, OSError | None, bool]:
    """Open ``lock_path`` and take it.

    Returns ``(handle, refusal, supported)``.  ``handle`` is None when the byte
    was not ours; ``refusal`` is the operating system's reason; ``supported``
    is False when this machine has no primitive to ask.
    """
    if primitives.msvcrt is None and primitives.fcntl is None:
        return None, OSError("本机没有可用的跨进程锁原语（msvcrt 与 fcntl 均未导出）"), False
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(lock_path, "a+")
    except OSError as exc:
        return None, exc, True
    try:
        for attempt in range(attempts):
            try:
                _take_one_byte(handle, primitives)
            except OSError as exc:
                if attempt == attempts - 1:
                    raise exc
                primitives.time.sleep(delay)
            else:
                return handle, None, True
    except OSError as exc:
        handle.close()
        return None, exc, True
    raise OSError(f"锁重试循环走完 {attempts} 次却没有判决")  # pragma: no cover - unreachable


def _release(handle: IO[str], primitives: LockPrimitives) -> None:
    """Put the lock back.  A refusal here is not fatal: closing the handle drops it."""
    try:
        _drop_one_byte(handle, primitives)
    except OSError:
        pass
    finally:
        handle.close()


@contextlib.contextmanager
def hold_sidecar(
    lock_path: Path,
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    delay: float = DEFAULT_DELAY,
    primitives: LockPrimitives | None = None,
) -> Iterator[LockOutcome]:
    """Hold the sidecar at ``lock_path`` for the body of the ``with`` block.

    Yields a :class:`LockOutcome` telling the caller whether the byte was
    actually ours.  It **never raises**: what a refused lock means differs per
    call site (a session checkpoint refuses the write, a catalog degrades it,
    a memory file must not lose the entry), and that decision belongs to the
    caller, not here.

    With neither lock primitive available the body runs unlocked and the
    outcome says so (``supported=False``) — a different situation from a
    refusal, and the caller may treat the two differently.
    """
    used = primitives or LockPrimitives()
    handle, refusal, supported = _acquire(
        lock_path, attempts=attempts, delay=delay, primitives=used
    )
    try:
        yield LockOutcome(
            held=handle is not None,
            refusal=refusal,
            attempts=attempts,
            delay=delay,
            supported=supported,
        )
    finally:
        if handle is not None:
            _release(handle, used)


__all__ = [
    "DEFAULT_ATTEMPTS",
    "DEFAULT_DELAY",
    "LOCK_BYTES",
    "LOCK_SUFFIX",
    "LockOutcome",
    "LockPrimitives",
    "hold_sidecar",
    "sidecar_path_for",
]
