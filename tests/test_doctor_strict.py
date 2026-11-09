"""M8-T693 — `minicc --doctor-strict` behaviour."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from minicc.setup import setup_workspace


def _git_init(cwd: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=cwd, check=True)


def _write_audit(ws: Path) -> None:
    audit = ws / ".minicc" / "audit.jsonl"
    audit.write_text('{"event": "doctor_test", "ts": 0}\n', encoding="utf-8")


def _run(args: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "minicc.main", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return proc.returncode, proc.stdout + proc.stderr


def test_doctor_strict_fails_on_flat_uninitialized_workspace(tmp_path: Path) -> None:
    rc, out = _run(["--doctor-strict"], tmp_path)
    assert rc == 1, out
    # Should mention fatal=0 and warn in the output but exit 1 anyway.
    assert "fatal=0" in out


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="doctor cannot treat NT mode bits as enforceable on Windows",
)
def test_doctor_strict_fails_when_web_token_is_world_readable(tmp_path: Path) -> None:
    _git_init(tmp_path)
    setup_workspace(tmp_path)
    _write_audit(tmp_path)
    # Make the token readable by all (0o644) on POSIX to force a fatal.
    token = tmp_path / ".minicc" / "web_token.json"
    token.chmod(0o644)
    rc, out = _run(["--doctor-strict"], tmp_path)
    # Strict must not pass when a fatal exists.
    assert rc == 1, out
