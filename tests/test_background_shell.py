"""M6-T4: explicit background shell — start, poll, kill, bounded & audited.

These spawn real child processes via the local interpreter (no mocks) and
assert the behaviour the roadmap lists as the exit criteria:

- ``run_in_background`` returns a ``shell_id`` immediately (long command does
  not block the tool turn);
- ``bash_output`` reads output incrementally (the cursor advances, no re-read);
- after ``kill_shell`` the shell reports as finished within ~1s and the process
  is reaped (no leftover process);
- a polled result is bounded (split_output head/tail, ≤ 6000 visible chars);
- detached starts (``&``) stay rejected even now that a real background mode
  exists;
- every background shell result carries the ``background_shell`` audit tag.

M8-T61 changed *how long the waits are allowed to take*, not what they decide.
The three polling loops used to carry a calendar constant (3.0s, 1.5s) and that
constant was thinner than reality here: measured on 2026-09-26 on a machine at
92% memory load, one bare ``python -c "print(1)"`` child cost 1.14-4.70s, while
the waits the budget has to cover peaked at 3.38s (20000-byte writer) and
3.64s (incremental first line).  A wall that a child start can exceed is not a
judgement about this code; it is a dice roll about scheduling, and when it lands
wrong it says ``assert None is not None``.

So the budget is now derived from the thing it is supposed to tolerate: this
run measures how long a bare child costs *here*, and each wait gets a multiple
of that, clamped to a floor and a ceiling so the policy cannot silently become
"infinite".  What the gates decide is unchanged and non-temporal: bytes appear,
the cursor advances, the render is bounded, a killed shell reports its exit code.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from minicc.tools.bash import (
    detached_command_reason,
    kill_background_shell,
    poll_background_shell,
    run_bash,
    start_background_shell,
)

#: The multiple is measured, not chosen for comfort: on a loaded host the slowest
#: wait in this family came in at 3.19x the same round's bare-child reference, and
#: the logged probe run (第三十五批 in docs/ROADMAP_TO_PRODUCT.md) never passed 0.95x
#: it.  12 keeps at least three times the worst observed ratio while the ceiling
#: below keeps it finite.
WAIT_RATIO = 12.0
#: Never shorter than this: a quiet machine measures ~0.2s for a child, and a
#: 2.4s budget would make the ratio the only thing standing between the gate and
#: a scheduling blip.
WAIT_FLOOR_S = 6.0
#: Never longer than this.  The ceiling is what makes the ratio honest: without it
#: a hung poll would be indistinguishable from a patient test.
WAIT_CEILING_S = 45.0
#: The calendar constant this batch replaced, kept so the record and the
#: failure messages can name what the budget used to be.
OLD_FIXED_WALL_S = 3.0

_START_COST: list[float] = []


def _py(script: str) -> str:
    # Quoted for both cmd.exe (Windows) and sh (posix) under shell=True.
    return f'"{sys.executable}" -c "{script}"'


def _bare_child_start_cost() -> float:
    """Seconds for a child interpreter to start, print one line, and exit.

    Measured once per test process and reused: it is a statement about the
    machine at this moment, and every wait in this file waits on a child.
    """
    if not _START_COST:
        command = _py("print(1)")
        started = time.monotonic()
        # errors= is not decoration: a text-mode capture without it is what
        # tests/test_subprocess_decoding.py counts as an offender.
        subprocess.run(command, shell=True, capture_output=True, text=True, errors="replace")
        _START_COST.append(time.monotonic() - started)
    return _START_COST[0]


def _wait_budget(reference_s: float) -> float:
    return min(WAIT_CEILING_S, max(WAIT_FLOOR_S, WAIT_RATIO * reference_s))


def _budget_note(budget_s: float | None, budget: float, reference_s: float) -> str:
    """Say where the number in a failure message actually came from.

    Two callers pass an explicit budget (the kill gate's 1.5s is a wall the exit
    standard names, the witness gate's 0.4s is tighter than the machine on
    purpose).  Printing the ratio for those would be a statement about a number
    that has nothing to do with it, and a reader would go adjust the wrong constant.
    """
    if budget_s is not None:
        return (
            f"budget={budget:.2f}s fixed by the caller, not derived from the "
            f"{reference_s:.2f}s bare-child start"
        )
    return (
        f"budget={WAIT_RATIO:g}x the {reference_s:.2f}s bare-child start, "
        f"floor={WAIT_FLOOR_S:g}s, ceiling={WAIT_CEILING_S:g}s"
    )


def _wait_for(
    what: str,
    probe: Callable[[], object | None],
    *,
    budget_s: float | None = None,
    poll_s: float = 0.1,
) -> object:
    """Poll until ``probe`` answers, or fail naming the wait.

    ``budget_s=None`` takes the derived budget; a caller that means to be tighter
    than the machine says so explicitly, and its number is the one reported on
    failure.  The reference is measured before the clock starts, so the cost of
    asking "how fast is this machine" is never charged to the wait.
    """
    reference = _bare_child_start_cost()
    budget = _wait_budget(reference) if budget_s is None else budget_s
    started = time.monotonic()
    polls = 0
    while True:
        polls += 1
        value = probe()
        if value is not None:
            return value
        elapsed = time.monotonic() - started
        if elapsed >= budget:
            raise AssertionError(
                f"gave up after {elapsed:.2f}s of a {budget:.2f}s budget "
                f"({_budget_note(budget_s, budget, reference)}, "
                f"polls={polls}) waiting for {what}"
            )
        time.sleep(poll_s)


def test_background_start_returns_immediately_and_is_audited(tmp_path: Path) -> None:
    shell = start_background_shell(
        _py("import time;print(1);time.sleep(5)"), tmp_path
    )
    try:
        assert shell.status == "ok"
        assert shell.data["background"] is True
        shell_id = shell.data["shell_id"]
        assert shell_id
        assert "background_shell" in shell.security_tags
        # Returned fast, well before the 5s the command would take in foreground.
        assert shell.data["pid"] > 0
    finally:
        kill_background_shell(shell_id)


def test_bash_output_reads_incrementally(tmp_path: Path) -> None:
    shell = start_background_shell(
        _py("import time;print('first');import sys;sys.stdout.flush();time.sleep(3);print('second')"),
        tmp_path,
    )
    shell_id = shell.data["shell_id"]
    try:
        first = _wait_for(
            "the first line to show up in a poll",
            lambda: (
                candidate
                if "first" in (candidate := poll_background_shell(shell_id)).render()
                else None
            ),
        )
        # The wait only proves the text appeared; that it arrived as *new* bytes
        # is the half the loop's own condition does not decide.
        assert first.data["new_bytes"] > 0, first.data
        # The second poll must not re-serve the already-read "first" line.
        again = poll_background_shell(shell_id)
        assert again.data["new_bytes"] == 0 or "first" not in again.render()
    finally:
        kill_background_shell(shell_id)


def test_kill_shell_reaps_process_within_a_second(tmp_path: Path) -> None:
    shell = start_background_shell(
        _py("import time;print(1);time.sleep(30)"), tmp_path
    )
    shell_id = shell.data["shell_id"]
    killed = kill_background_shell(shell_id)
    assert killed.status == "ok"
    assert killed.data["was_running"] is True

    # Waiting for the reap is a different quantity from waiting for a child to
    # start: this one is bounded by the wall the exit standard names, so it stays
    # a constant and says so in its own words when it misses.
    finished = _wait_for(
        "the killed shell to report finished with an exit code",
        lambda: (
            poll
            if (poll := poll_background_shell(shell_id)).data["finished"]
            else None
        ),
        budget_s=OLD_FIXED_WALL_S / 2,
    )
    assert finished.data["exit_code"] is not None


def test_background_output_is_bounded(tmp_path: Path) -> None:
    shell = start_background_shell(
        _py("import sys;sys.stdout.write('x'*20000);sys.stdout.flush()"), tmp_path
    )
    shell_id = shell.data["shell_id"]
    try:
        result = _wait_for(
            "any new byte to reach the poller",
            lambda: (
                candidate
                if (candidate := poll_background_shell(shell_id)).data["new_bytes"] > 0
                else None
            ),
        )
        # split_output keeps head+tail <= 6000; render adds a truncation marker.
        assert result.truncated is True
        assert len(result.render()) <= 7000
    finally:
        kill_background_shell(shell_id)


def test_run_in_background_dispatches_and_detached_still_rejected(tmp_path: Path) -> None:
    # Foreground detached-start stays blocked (the guard was tightened, not loosened).
    assert detached_command_reason("start /min notepad &") is not None
    blocked = run_bash("sleep 5 &", tmp_path, run_in_background=True)
    assert blocked.status == "error"
    assert blocked.data["code"] == "detached_process_blocked"

    started = run_bash(_py("import time;time.sleep(3)"), tmp_path, run_in_background=True)
    assert started.status == "ok"
    kill_background_shell(started.data["shell_id"])


def test_unknown_shell_id_reports_available(tmp_path: Path) -> None:
    missing = poll_background_shell("bg-doesnotexist")
    assert missing.status == "error"
    assert "available" in missing.data
    killed = kill_background_shell("bg-doesnotexist")
    assert killed.status == "error"


def test_the_wait_budget_follows_the_measured_child(tmp_path: Path) -> None:
    """The budget has to be a function of this machine, and still be finite.

    Three things, none of which a constant can express at once: it grows with the
    cost of the child it waits for, it does not run away to "wait forever", and on
    a machine like this one it is *above* the calendar wall it replaced - which is
    the whole defect, stated as an inequality.
    """
    assert _wait_budget(0.0) == WAIT_FLOOR_S, "a fast machine must not get a zero budget"
    assert _wait_budget(10_000.0) == WAIT_CEILING_S, "the ceiling is what keeps this finite"
    assert _wait_budget(1.0) < _wait_budget(2.0) <= 2 * _wait_budget(1.0), "monotone, sub-linear"
    reference = _bare_child_start_cost()
    budget = _wait_budget(reference)
    assert budget > reference, (
        f"a {reference:.2f}s child cannot be waited for in {budget:.2f}s; this host has run "
        f"past the ceiling, so raise WAIT_CEILING_S rather than deleting it"
    )
    assert WAIT_CEILING_S > WAIT_FLOOR_S > OLD_FIXED_WALL_S
    # The measurement is real, not a stubbed number: a child that prints exists.
    assert reference > 0.0, "a zero child start cost would make the ratio meaningless"
    # And the failure text must not claim this provenance for a caller that
    # supplied its own number - see the record of what the first version printed.
    derived = _budget_note(None, _wait_budget(3.0), 3.0)
    assert f"budget={WAIT_RATIO:g}x the 3.00s bare-child start" in derived, derived
    assert "fixed by the caller" not in derived, derived
    explicit = _budget_note(OLD_FIXED_WALL_S / 2, OLD_FIXED_WALL_S / 2, 7.47)
    assert "budget=1.50s fixed by the caller" in explicit, explicit
    assert f"{WAIT_RATIO:g}x" not in explicit, (
        f"an explicit budget may not borrow the ratio's provenance: {explicit}"
    )


def test_a_shell_that_never_answers_reddens_with_the_wait_written_out(tmp_path: Path) -> None:
    """The patience has a failure branch, and it is readable.

    A silent wait would be indistinguishable from a patient one, so this forces
    the timeout with a budget deliberately tighter than the machine: a real
    background shell that writes nothing, ``print`` only after 20s.  The gate
    asserts the raise happens *and* that the message names the elapsed wait, the
    budget, the reference it came from and what was being waited for - the four
    numbers that ``assert None is not None`` used to hide.  It also asserts the
    message says where that budget came from: this caller fixed it at 0.4s, so the
    text must own up to the caller and must not borrow the ratio's provenance.
    """
    shell = start_background_shell(
        _py("import time;time.sleep(20);print(1)"), tmp_path
    )
    shell_id = shell.data["shell_id"]
    try:
        try:
            _wait_for(
                "output from a shell that writes nothing",
                lambda: (
                    candidate
                    if (candidate := poll_background_shell(shell_id)).data["new_bytes"] > 0
                    else None
                ),
                budget_s=0.4,
                poll_s=0.05,
            )
        except AssertionError as failure:
            message = str(failure)
        else:
            raise AssertionError("the tight budget did not fire: the wait is not bounded")
        for fragment in ("0.40s budget", "waiting for output from a shell that writes nothing"):
            assert fragment in message, f"{fragment!r} missing from {message!r}"
        assert f"{_bare_child_start_cost():.2f}s bare-child start" in message, message
        assert "fixed by the caller" in message, message
        assert f"{WAIT_RATIO:g}x the" not in message, (
            f"a caller-supplied budget borrowed the ratio's provenance: {message!r}"
        )
    finally:
        kill_background_shell(shell_id)
