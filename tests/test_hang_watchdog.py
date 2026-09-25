"""M8-T50: an overrunning test is reported, and a stalled one leaves a stack behind.

Both halves are needed because each has a cheap way to look green for the wrong reason: a
watchdog that failed everything would satisfy the positive gate, and one that never fired
would satisfy the negative one.  The mechanism is exercised in nested pytest sessions -
in-process it would fail this very file.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE = REPO_ROOT / "tests" / "test_hang_watchdog_probe_tmp.py"


def _nested_session(sleep_seconds: float, limit: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["MINICC_TEST_HANG_LIMIT"] = limit
    PROBE.write_text(
        "import time\n\n\ndef test_probe_sleep() -> None:\n    time.sleep("
        + repr(sleep_seconds)
        + ")\n",
        encoding="utf-8",
    )
    try:
        return subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", str(PROBE)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
            encoding="utf-8",
            errors="replace",
            env={**env, "PYTHONIOENCODING": "utf-8"},
        )
    finally:
        PROBE.unlink(missing_ok=True)


def test_a_test_inside_the_bound_is_left_alone() -> None:
    """The negative half: inside the bound there is no failure and no dump."""
    proc = _nested_session(sleep_seconds=0.2, limit="30")
    assert proc.returncode == 0, (proc.returncode, proc.stdout[-400:], proc.stderr[-400:])
    assert "1 passed" in proc.stdout, proc.stdout[-400:]
    assert "MINICC_TEST_HANG_LIMIT" not in proc.stderr, proc.stderr[-400:]


def test_a_test_that_overshoots_the_bound_is_reported_as_failed() -> None:
    """The positive half: the run keeps its report, and the slow test turns red."""
    proc = _nested_session(sleep_seconds=3.0, limit="1")
    assert proc.returncode != 0, (proc.returncode, proc.stdout[-400:])
    assert "1 failed" in proc.stdout, proc.stdout[-400:]
    assert "MINICC_TEST_HANG_LIMIT" in proc.stdout + proc.stderr, (proc.stdout[-400:], proc.stderr[-400:])


def test_the_watchdog_can_be_switched_off_but_never_invented(monkeypatch) -> None:
    """Absent = default; touched-but-useless = off, and the default is far from noise."""
    import conftest

    for off in ("0", "-1", "not-a-number", ""):
        monkeypatch.setenv("MINICC_TEST_HANG_LIMIT", off)
        assert conftest.hang_limit_seconds() is None, off
    monkeypatch.delenv("MINICC_TEST_HANG_LIMIT", raising=False)
    assert conftest.hang_limit_seconds() == conftest.DEFAULT_HANG_LIMIT_SECONDS
    assert conftest.DEFAULT_HANG_LIMIT_SECONDS >= 600.0, "a bound inside load noise is no bound"
