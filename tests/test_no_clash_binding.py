"""M8-T1343: the machine must have no active Clash Verge binding.

Runs scripts/check_no_clash.py and requires all six checks to pass. This makes
the "Clash retired" state a permanent, runnable guarantee rather than a claim
in a ledger entry.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "scripts" / "check_no_clash.py"


def test_no_active_clash_binding() -> None:
    # Drop inherited proxy vars so the gate reads the real machine state. Pin
    # the child's stdout/stderr codec INLINE in env= — a parent-only decoder is
    # half-pinned and the subprocess-decoding gate rejects it on Windows.
    proxy_free = dict(os.environ)
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                "http_proxy", "https_proxy", "all_proxy"):
        proxy_free.pop(key, None)
    result = subprocess.run(
        [sys.executable, str(CHECK)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(ROOT), env=dict(proxy_free, PYTHONIOENCODING="utf-8"),
        timeout=60, check=False,
    )
    assert result.returncode == 0, f"a Clash binding remains:\n{result.stdout}\n{result.stderr}"
    assert "6/6 checks passed" in result.stdout, result.stdout
