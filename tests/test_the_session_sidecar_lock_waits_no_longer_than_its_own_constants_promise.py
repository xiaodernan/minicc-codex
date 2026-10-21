"""M8-T353: the session sidecar lock must wait exactly what its constants promise.

``minicc/session.py`` budgets ``_LOCK_ATTEMPTS = 400`` times ``_LOCK_RETRY_DELAY =
0.05``; read that pair and the ceiling looks like twenty seconds.  Two things made that
reading false:

* the retry loop passed ``msvcrt.LK_LOCK``, a mode whose refusal is not an answer - the
  C runtime retries on its own for seconds before it admits defeat - so each iteration
  cost a CRT stall rather than the delay the loop budgets, and the give-up path (400
  iterations plus a final try) was minutes-to-an-hour, charged inside HTTP request
  threads (``web.py`` calls ``store.save`` per message).  The sibling that shares this
  sidecar naming rule measured the same stall and chose the other mode: ``minicc/workspaces.py``.
* the POSIX branch never entered the loop at all: ``fcntl.flock(fd, LOCK_EX)`` is asked
  for without ``LOCK_NB``, so it waits with no ceiling, and a refusal there would escape
  as a bare ``OSError`` instead of the ``SessionError`` every caller catches.

Blind spots, stated rather than hidden: the POSIX leg runs on a stand-in ``fcntl``, so it
proves the flag and the exception class the shipped code asks for - not that the kernel
blocks forever.  Nothing here changes who may write: the lock is still
best-effort-exclusive, still held only across ``_write_payload_at``'s read-modify-write,
and the give-up still raises - unlike the workspace catalog, which degrades (M8-T265).
"""

from __future__ import annotations

import ast
import contextlib
import msvcrt
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Any, Iterator

import pytest

from minicc import session as session_module
from minicc.session import SessionError, _cross_process_lock

#: Attempts the contended legs ask for.  Small on purpose: those legs judge the shape of
#: one refusal, and a pre-fix run pays one C-runtime stall per attempt, so this number
#: also bounds how long the reverse control takes.
SHORT_ATTEMPTS = 4
#: A neighbour that will not let go, for longer than any contended leg below.
STUBBORN_SECONDS = 120.0

PKG = Path(session_module.__file__).resolve().parent
CHILD = textwrap.dedent(
    """
    import msvcrt, sys, time
    from pathlib import Path

    path, verb = Path(sys.argv[1]), sys.argv[2]
    handle = open(path, "a+")
    handle.seek(0)
    if verb == "hold":
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        print("HELD", flush=True)
        time.sleep(float(sys.argv[3]))
        print("RELEASED", flush=True)
    else:
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            print("BUSY")
        else:
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            print("FREE")
    """
)


def _child_script(tmp_path: Path) -> Path:
    script = tmp_path / "sidecar_child.py"
    script.write_text(CHILD, encoding="utf-8", newline="\n")
    return script


def _hold(tmp_path: Path, lock_path: Path, seconds: float) -> subprocess.Popen:
    """Start a neighbour that takes the byte, and do not return until it holds it.

    The holder itself uses the immediate mode: a holder that parks would make a leg
    reporting "the neighbour refused us" be reporting about its own holder.
    """
    proc = subprocess.Popen(
        [sys.executable, str(_child_script(tmp_path)), str(lock_path), "hold", str(seconds)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert proc.stdout is not None, "the holder child has no transcript to read"
    first = proc.stdout.readline().strip()
    assert first == "HELD", (
        f"the neighbour never took the sidecar ({first!r}): a leg that claims a refusal "
        "must first prove the other side was in a position to refuse"
    )
    return proc


def _drop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.kill()
    proc.communicate(timeout=60)


def _sidecar_state(tmp_path: Path, lock_path: Path) -> str:
    """Ask the OS, from another process, whether the byte is free.

    A second handle inside *this* process is refused too, so an in-process probe would
    answer BUSY even after a correct unlock and prove nothing.
    """
    done = subprocess.run(
        [sys.executable, str(_child_script(tmp_path)), str(lock_path), "probe"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, f"the probe child died: {done.stdout!r} {done.stderr!r}"
    state = done.stdout.strip()
    assert state in {"FREE", "BUSY"}, f"the probe answered {state!r}, not FREE or BUSY"
    return state


@contextlib.contextmanager
def _attempt_budget(count: int) -> Iterator[None]:
    """Put the module's own attempt budget at a value this leg can afford to wait out."""
    previous = session_module._LOCK_ATTEMPTS
    session_module._LOCK_ATTEMPTS = count
    try:
        yield
    finally:
        session_module._LOCK_ATTEMPTS = previous


@contextlib.contextmanager
def _instrumented() -> Iterator[dict[str, Any]]:
    """Rebind the session module's ``msvcrt`` and ``time`` to recording delegates.

    Every call reaches the real primitive, so "it refused" is the operating system's
    answer and not the fixture's.  The module attributes are rebound, not the stdlib
    modules, so nothing else in the process sees the proxy.
    """
    real_msvcrt = session_module.msvcrt
    real_time = session_module.time
    seen: dict[str, Any] = {"modes": [], "durations": [], "sleeps": [], "attempts": []}

    class _Msvcrt:
        def __getattr__(self, name: str) -> Any:
            return getattr(real_msvcrt, name)

        def locking(self, fd: int, mode: int, nbytes: int) -> None:
            start = time.monotonic()
            try:
                real_msvcrt.locking(fd, mode, nbytes)
            finally:
                taken = time.monotonic() - start
                seen["modes"].append(mode)
                seen["durations"].append(taken)
                seen["attempts"].append((mode, taken))

    class _Time:
        def __getattr__(self, name: str) -> Any:
            return getattr(real_time, name)

        def sleep(self, seconds: float) -> None:
            seen["sleeps"].append(seconds)
            real_time.sleep(seconds)

    previous = (session_module.msvcrt, session_module.time)
    session_module.msvcrt, session_module.time = _Msvcrt(), _Time()
    try:
        yield seen
    finally:
        session_module.msvcrt, session_module.time = previous


@contextlib.contextmanager
def _contended(tmp_path: Path) -> Iterator[dict[str, Any]]:
    """A neighbour holds the byte for the whole leg while the caller drives one acquire.

    The leg fills in ``outcome`` (what escaped), ``entered`` and ``seconds``; the budget
    in force is recorded so the assertions can be written as a function of it.
    """
    lock = tmp_path / "session.json.lock"
    holder = _hold(tmp_path, lock, STUBBORN_SECONDS)
    try:
        with _attempt_budget(SHORT_ATTEMPTS), _instrumented() as seen:
            started = time.monotonic()
            outcome: BaseException | None = None
            entered = False
            try:
                with _cross_process_lock(lock):
                    entered = True
            except BaseException as exc:  # noqa: BLE001 - the exception class is the reading
                outcome = exc
            seen["outcome"] = outcome
            seen["entered"] = entered
            seen["seconds"] = time.monotonic() - started
            seen["ceiling"] = SHORT_ATTEMPTS * session_module._LOCK_RETRY_DELAY
            yield seen
    finally:
        _drop(holder)


def _seconds_named_in(text: str) -> list[float]:
    """Every ``<number>s`` the product actually says, so a claim is checked as a number.

    Matching on the digit rather than on a fixed sentence keeps this leg honest when the
    wording changes, and keeps ``SHORT_ATTEMPTS`` from being baked into a string.
    """
    return [float(found) for found in re.findall(r"(\d+(?:\.\d+)?)\s*s", text)]


@contextlib.contextmanager
def _recorded_backoffs() -> Iterator[list[float]]:
    """Record the loop's own sleeps, leaving both lock primitives alone.

    A leg that swaps out ``msvcrt`` to reach the POSIX branch cannot also use
    ``_instrumented``, which rebinds that same name: the shipped code would then still
    take the Windows branch, and the leg would report on its own fixture.
    """
    real_time = session_module.time
    slept: list[float] = []

    class _Time:
        def __getattr__(self, name: str) -> Any:
            return getattr(real_time, name)

        def sleep(self, seconds: float) -> None:
            slept.append(seconds)
            real_time.sleep(seconds)

    previous = session_module.time
    session_module.time = _Time()
    try:
        yield slept
    finally:
        session_module.time = previous


def test_a_refused_attempt_answers_within_one_backoff_step(tmp_path: Path) -> None:
    """The defect in one clause: a refusal cost a C-runtime stall, not the budgeted delay.

    The bound is a ratio taken inside the same run - one attempt against one backoff step
    - so a loaded machine moves both sides together instead of faking a red.
    """
    with _contended(tmp_path) as leg:
        assert leg["modes"], "the shipped loop never called the lock primitive"
        slowest = max(leg["durations"])
        assert slowest < session_module._LOCK_RETRY_DELAY, (
            f"one refused attempt took {slowest:.3f}s while the loop budgets "
            f"{session_module._LOCK_RETRY_DELAY}s per attempt: the mode in use parks the "
            "caller inside the C runtime, so the ceiling the constants advertise is a fiction"
        )


def test_the_retry_loop_asks_for_the_mode_that_does_not_park_the_caller(tmp_path: Path) -> None:
    """Name the mode, because the wait the loop can promise depends on which one it is."""
    with _contended(tmp_path) as leg:
        parked = [mode for mode in leg["modes"] if mode == msvcrt.LK_LOCK]
        assert not parked, (
            f"{len(parked)} of {len(leg['modes'])} attempts used LK_LOCK, the blocking "
            f"mode; one refusal measured {max(leg['durations']):.3f}s against a "
            f"{session_module._LOCK_RETRY_DELAY}s budget"
        )
        assert set(leg["modes"]) == {msvcrt.LK_NBLCK}, (
            f"a contended acquire asked for modes {sorted(set(leg['modes']))}, expected "
            f"only LK_NBLCK ({msvcrt.LK_NBLCK})"
        )


def test_the_loop_backs_off_by_the_budget_it_advertises(tmp_path: Path) -> None:
    """Immediate attempts still need the loop's own sleep, or 400 of them is a spin."""
    with _contended(tmp_path) as leg:
        assert leg["sleeps"], "the retry loop never backed off: it re-asked with no delay at all"
        assert set(leg["sleeps"]) == {session_module._LOCK_RETRY_DELAY}, (
            f"the loop slept {leg['sleeps']}, none of it the advertised "
            f"{session_module._LOCK_RETRY_DELAY}s"
        )
        assert len(leg["sleeps"]) >= SHORT_ATTEMPTS - 1, (
            f"{len(leg['sleeps'])} backoffs for a {SHORT_ATTEMPTS}-attempt budget: the "
            "loop gave up before it spent what it promised"
        )


def test_the_give_up_names_the_ceiling_it_just_spent(tmp_path: Path) -> None:
    """A wait an operator cannot bound is a wait they cannot reason about."""
    with _contended(tmp_path) as leg:
        outcome = leg["outcome"]
        assert isinstance(outcome, SessionError), (
            f"the give-up raised {type(outcome).__name__}: {outcome}"
        )
        text = str(outcome)
        named = _seconds_named_in(text)
        assert named, f"the refusal says {text!r} and never names a bound"
        ceiling = leg["ceiling"]
        assert any(ceiling <= value <= ceiling * 1.5 for value in named), (
            f"the refusal says {text!r} about {named} seconds, while the budget in force "
            f"was {SHORT_ATTEMPTS} x {session_module._LOCK_RETRY_DELAY} = {ceiling:.2f}s"
        )


def test_a_neighbour_that_lets_go_inside_the_ceiling_still_lets_the_writer_in(tmp_path: Path) -> None:
    """The other half: a short-lived neighbour is waited out, not refused."""
    lock = tmp_path / "session.json.lock"
    holder = _hold(tmp_path, lock, 0.3)
    started = time.monotonic()
    try:
        with _cross_process_lock(lock):
            entered = True
    except SessionError as exc:
        _drop(holder)
        pytest.fail(f"gave up on a neighbour that had already let go: {exc}")
    seconds = time.monotonic() - started
    _drop(holder)
    assert entered, "the context exited without running its body and without raising"
    ceiling = session_module._LOCK_ATTEMPTS * session_module._LOCK_RETRY_DELAY
    assert seconds < ceiling, (
        f"the writer got in, but only after {seconds:.1f}s - past the {ceiling:.1f}s the "
        "constants advertise, which is exactly the waiting this file exists to remove"
    )


def test_the_sidecar_holds_for_the_body_and_is_free_after_it(tmp_path: Path) -> None:
    """The lock must still mean something: BUSY inside the body, FREE outside it."""
    lock = tmp_path / "session.json.lock"
    with _cross_process_lock(lock):
        assert _sidecar_state(tmp_path, lock) == "BUSY", (
            "the sidecar was free while the writer held it, so nothing was serialised"
        )
    assert _sidecar_state(tmp_path, lock) == "FREE", (
        "the byte stayed taken after the body returned, so every later writer pays the ceiling"
    )


def test_an_uncontended_writer_takes_the_byte_on_the_first_attempt(tmp_path: Path) -> None:
    """The common path must not have become a retry loop."""
    lock = tmp_path / "session.json.lock"
    with _instrumented() as seen:
        with _cross_process_lock(lock):
            entered = True
    assert entered, "the body never ran"
    assert seen["modes"] == [msvcrt.LK_NBLCK, msvcrt.LK_UNLCK], (
        f"an uncontended write recorded {seen['modes']}: expected one take and one release"
    )
    assert not seen["sleeps"], f"an uncontended acquire backed off anyway: {seen['sleeps']}"


def test_the_posix_branch_also_asks_for_a_non_blocking_lock(tmp_path: Path) -> None:
    """The other plane, cheaply: a stand-in ``fcntl`` shows the flag the code passes.

    This cannot show a kernel blocking forever.  It shows that the shipped POSIX branch
    asks for ``LOCK_EX`` with no ``LOCK_NB`` - so it never enters the retry loop the
    Windows branch has - and that a refusal escapes as something other than the
    ``SessionError`` every caller catches (``main.py:96``, ``webserver.py:695``).
    """
    lock = tmp_path / "session.json.lock"
    asked: list[int] = []

    class _Fcntl:
        LOCK_EX = 2
        LOCK_NB = 4
        LOCK_UN = 8

        def flock(self, fd: int, flag: int) -> None:
            """Record the flag, then refuse: the leg's premise is a held lock."""
            asked.append(flag)
            raise OSError(11, "Resource temporarily unavailable")

    previous = (session_module.msvcrt, session_module.fcntl)
    session_module.msvcrt, session_module.fcntl = None, _Fcntl()  # type: ignore[assignment]
    try:
        with _attempt_budget(SHORT_ATTEMPTS), _recorded_backoffs() as sleeps:
            started = time.monotonic()
            outcome: BaseException | None = None
            try:
                with _cross_process_lock(lock):
                    pass
            except BaseException as exc:  # noqa: BLE001 - the class is the reading
                outcome = exc
            seconds = time.monotonic() - started
    finally:
        session_module.msvcrt, session_module.fcntl = previous  # type: ignore[assignment]
    assert asked, "the POSIX branch never called flock, so this leg measured nothing"
    assert asked[0] & _Fcntl.LOCK_NB, (
        f"flock was asked for with flag {asked[0]}: without LOCK_NB this branch waits with "
        "no ceiling, while the constants promise a budgeted loop"
    )
    assert isinstance(outcome, SessionError), (
        f"a refused POSIX lock escaped as {type(outcome).__name__} after {seconds:.2f}s "
        f"({len(asked)} flock calls, {len(sleeps)} backoffs); callers catch SessionError, "
        "so anything else walks past the handlers that know what to do with it"
    )


def test_a_machine_with_neither_primitive_still_runs_the_body_unlocked(tmp_path: Path) -> None:
    """The no-op degradation is documented behaviour, and a rewrite can quietly lose it.

    With both names set to ``None`` the shipped code must run the body and must not raise:
    there is no lock to wait for.  An arm that turns the guard into a crash - or into an
    endless loop over a primitive that does not exist - is caught here.  The sidecar itself
    is the second half of the claim: a writer that has nothing to take must not open it and
    report ``locked=True`` anyway, because the file it leaves behind is the thing every
    later reader trusts.
    """
    lock = tmp_path / "session.json.lock"
    previous = (session_module.msvcrt, session_module.fcntl)
    session_module.msvcrt, session_module.fcntl = None, None  # type: ignore[assignment]
    try:
        with _cross_process_lock(lock):
            entered = True
    except BaseException as exc:  # noqa: BLE001 - the claim is that nothing escapes
        pytest.fail(f"the unsupported-platform path raised {type(exc).__name__}: {exc}")
    finally:
        session_module.msvcrt, session_module.fcntl = previous  # type: ignore[assignment]
    assert entered, "the body was skipped on a platform with no lock primitive"
    assert not lock.exists(), (
        f"{lock.name} was opened although this machine has no lock primitive to ask. "
        "Two shapes reach this: the early return deleted (the helper then finds no "
        "primitive, raises nothing, and the loop reports ``locked=True`` for a byte "
        "nobody handed out), or the file opened before anyone checked whether a "
        "primitive exists (the shape this file replaced). Either way a ``*.json.lock`` "
        "is left behind that no writer ever held, and every later reader trusts it."
    )


def test_no_bounded_retry_loop_in_the_package_parks_on_the_blocking_mode() -> None:
    """The class, not just this file: ``workspaces.py`` learned this and got it right.

    A walk over every ``msvcrt.locking(...)`` call site in the package, reading the mode
    argument as a name rather than as a substring.  Removing a call is not what this
    covers - the contended legs above are what prove a call exists and answers.
    """
    offenders: list[str] = []
    for path in sorted(PKG.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr != "locking" or not isinstance(node.func.value, ast.Name):
                continue
            if node.func.value.id != "msvcrt" or len(node.args) < 2:
                continue
            mode = node.args[1]
            if isinstance(mode, ast.Attribute) and mode.attr == "LK_LOCK":
                offenders.append(f"{path.relative_to(PKG)}:{node.lineno}")
    assert offenders == [], (
        f"{offenders} lock with LK_LOCK, the mode whose refusal parks the caller inside "
        "the C runtime; a loop that budgets its own delay must ask the immediate question"
    )
