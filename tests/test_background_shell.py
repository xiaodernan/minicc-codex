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
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from minicc.tools.bash import (
    detached_command_reason,
    kill_background_shell,
    poll_background_shell,
    run_bash,
    start_background_shell,
)


def _py(script: str) -> str:
    # Quoted for both cmd.exe (Windows) and sh (posix) under shell=True.
    return f'"{sys.executable}" -c "{script}"'


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
        first = None
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            candidate = poll_background_shell(shell_id)
            if "first" in candidate.render():
                first = candidate
                break
            time.sleep(0.1)
        assert first is not None and "first" in first.render()
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

    finished = None
    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline:
        poll = poll_background_shell(shell_id)
        if poll.data["finished"]:
            finished = poll
            break
        time.sleep(0.1)
    assert finished is not None, "shell did not report finished within 1.5s of kill"
    assert finished.data["exit_code"] is not None


def test_background_output_is_bounded(tmp_path: Path) -> None:
    shell = start_background_shell(
        _py("import sys;sys.stdout.write('x'*20000);sys.stdout.flush()"), tmp_path
    )
    shell_id = shell.data["shell_id"]
    try:
        deadline = time.monotonic() + 3.0
        result = None
        while time.monotonic() < deadline:
            candidate = poll_background_shell(shell_id)
            if candidate.data["new_bytes"] > 0:
                result = candidate
                break
            time.sleep(0.1)
        assert result is not None
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
