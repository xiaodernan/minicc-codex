"""M8-T569 — the hang-limit rewrite has one reader.

A test that crosses the hang bound is rewritten by conftest.py's hooks from
``passed`` to ``failed`` - deliberately (M8-T50: the run must not silently
swallow a hung test).  The cost of that choice, recorded since M8-T522: the
summary line files the hang under the same word as an assertion verdict,
and only the ``longrepr`` text tells them apart — if you read it at all.

This gate pins the one thing the word lacked: a *reader* for the hang class.
After the fix, the session prints one named line listing every test the
hook rewrote, so a CI reader sees the hang class distinctly without opening
the report body.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_a_hang_crosser_gets_its_own_named_line() -> None:
    probe_dir = REPO / ".pytest_tmp_hang_probe"
    shutil.rmtree(probe_dir, ignore_errors=True)
    probe_dir.mkdir(parents=True, exist_ok=True)
    try:
        probe = probe_dir / "test_hang_probe.py"
        probe.write_text(
            "import time\n\n"
            "def test_slow():\n"
            "    time.sleep(0.2)\n"
            "\n"
            "def test_fast():\n"
            "    assert True\n",
            encoding="utf-8",
        )
        env = dict(os.environ, MINICC_TEST_HANG_LIMIT="0.05", PYTHONIOENCODING="utf-8")
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--no-header", str(probe)],
            cwd=REPO,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=120,
        )
        combined = (result.stdout or "") + (result.stderr or "")
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)
    assert result.returncode == 1, f"the hang crosser must fail: {combined[-800:]}"
    assert "test_slow" in combined, combined[-800:]
    assert "MINICC_TEST_HANG_LIMIT: 1 test crossed the hang bound (not a verdict): " in combined, (
        "the session-finish reader never spoke for the hang class; the summary "
        f"files the crosser under the same word as a verdict\n{combined[-2000:]}"
    )
    assert "test_hang_probe.py::test_slow" in combined, combined[-800:]


def test_the_clean_run_does_not_print_the_hang_line() -> None:
    """Anti-vacuity: the reader must be silent when nothing crossed the bound."""
    probe_dir = REPO / ".pytest_tmp_hang_probe_clean"
    shutil.rmtree(probe_dir, ignore_errors=True)
    probe_dir.mkdir(parents=True, exist_ok=True)
    try:
        probe = probe_dir / "test_clean_probe.py"
        probe.write_text("def test_fast():\n    assert True\n", encoding="utf-8")
        env = dict(os.environ, MINICC_TEST_HANG_LIMIT="0.05", PYTHONIOENCODING="utf-8")
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--no-header", str(probe)],
            cwd=REPO,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=120,
        )
        combined = (result.stdout or "") + (result.stderr or "")
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)
    assert result.returncode == 0, combined[-800:]
    assert "crossed the hang bound" not in combined, combined[-800:]
