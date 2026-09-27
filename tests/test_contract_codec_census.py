"""M8-T58's sibling cell: the file-contract grader must not judge content it cannot read.

Measured before writing (all three shapes): a workspace file written in the
host's legacy codepage is read by the old ``errors="replace"`` decoder as
replacement characters, which makes a non-ASCII ``contains`` criterion fail on
correct work *and* makes a non-ASCII ``not_contains`` criterion **pass while the
forbidden text is physically in the file**. The ASCII markers used by every
shipped task survive replacement, so the false green was latent - reachable the
moment anyone wrote a Chinese forbidden-marker rule, which is the normal style
in this repository.

The tests drive the shipped grader string itself, so they break when it drifts.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from minicc.bench_tasks import _FILE_CONTRACT_GRADER

REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS = REPO_ROOT / "benchmarks" / "tasks.v2.json"
COMPLETE = "MINICC_FILE_CONTRACT_COMPLETE"
MARKER = "禁止标记"


def _grade(workspace: Path, spec: dict) -> subprocess.CompletedProcess[str]:
    script = workspace / "_grader.py"
    script.write_text(_FILE_CONTRACT_GRADER, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(script), str(workspace)],
        input=json.dumps(spec),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        # The child writes the refusal (file name, byte offset) to stderr and this
        # parent decodes it as utf-8: owning only one end is the defect this file
        # exists to refuse, and tests/test_subprocess_decoding.py says so.
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        cwd=str(workspace),
        timeout=120,
    )


def test_a_utf8_workspace_still_grades_and_the_census_is_printed(tmp_path: Path) -> None:
    """Control: the refusal must not eat the case that used to work."""
    (tmp_path / "report.md").write_text(f"ok {MARKER} fine\n", encoding="utf-8")
    proc = _grade(tmp_path, {"files": [{"path": "report.md", "contains": MARKER}]})
    items = [task for task in json.loads(TASKS.read_text(encoding="utf-8"))]
    file_items = [item for task in items for item in (task.get("grader") or {}).get("files") or []]
    non_ascii = [
        (task["id"], key, item[key])
        for task in items
        for item in (task.get("grader") or {}).get("files") or []
        for key in ("contains", "not_contains", "equals", "regex")
        if isinstance(item.get(key), str) and any(ord(ch) > 127 for ch in item[key])
    ]
    assert COMPLETE in proc.stdout, proc.stdout + proc.stderr
    assert proc.returncode == 0, proc.stderr
    assert file_items, "no shipped task exercises the file-contract grader at all"
    assert non_ascii == [], (
        f"{len(non_ascii)} of {len(file_items)} shipped file-contract items now match a "
        f"non-ascii marker: {non_ascii} - re-read whether refuse-to-judge is the right "
        "verdict for them (this count is reported, not pinned: it moves with the tasks)"
    )


def test_a_legacy_codepage_file_cannot_silence_a_forbidden_marker(tmp_path: Path) -> None:
    """The false green: forbidden text present, criterion satisfied by encoding."""
    (tmp_path / "notes.txt").write_bytes(f"prefix {MARKER} suffix\n".encode("gbk"))
    proc = _grade(tmp_path, {"files": [{"path": "notes.txt", "not_contains": MARKER}]})
    assert COMPLETE not in proc.stdout, (
        "a non-utf-8 file satisfied not_contains purely by being unreadable; "
        f"the grader graded replacement characters and reported success: {proc.stdout!r}"
    )
    assert proc.returncode == 2, (
        f"expected 'cannot judge' (2), got {proc.returncode}: {proc.stderr}"
    )
    assert "not valid utf-8 at byte" in proc.stderr, proc.stderr


def test_a_legacy_codepage_file_cannot_fake_a_missing_substring(tmp_path: Path) -> None:
    """Same cell, opposite direction: correct work used to grade as a failure."""
    (tmp_path / "notes.txt").write_bytes(f"prefix {MARKER} suffix\n".encode("gbk"))
    proc = _grade(tmp_path, {"files": [{"path": "notes.txt", "contains": MARKER}]})
    assert proc.returncode == 2, (
        "an author's correct non-utf-8 file must not be graded as a content "
        f"mismatch either: {proc.returncode} {proc.stderr}"
    )
    assert "refusing to match markers" in proc.stderr, proc.stderr


def test_the_refusal_names_the_byte_offset_not_a_bare_exception(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_bytes("中文\n".encode("gbk"))
    proc = _grade(tmp_path, {"files": [{"path": "notes.txt", "contains": "x"}]})
    line = next((row for row in proc.stderr.splitlines() if "not valid utf-8" in row), "")
    assert "notes.txt" in line and "byte" in line, (
        f"the reader must say which file and where it stopped reading: {proc.stderr!r}"
    )
    assert proc.returncode == 2, proc.stderr


def test_grader_source_no_longer_swallows_decode_errors() -> None:
    """Pins the mechanism, so a later refactor cannot quietly restore it."""
    assert 'errors="replace"' not in _FILE_CONTRACT_GRADER, (
        "the file-contract reader went back to replacing undecodable bytes; "
        "that is exactly what let not_contains pass on unreadable files"
    )
    assert "raw.decode(" in _FILE_CONTRACT_GRADER, _FILE_CONTRACT_GRADER
