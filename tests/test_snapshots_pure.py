"""Independent fence tests for ``minicc.snapshots`` pure path/digest logic.

These pin the security-critical path-handling boundaries without touching git,
the network, or the journal on disk:
- ``_relative``: normalizes separators and rejects traversal / null / drive /
  absolute / ``..`` / internal ``.git`` & ``.minicc`` paths.
- ``_digest``: sha256 of a file, ``None`` when missing, raises on a directory.
- ``_summary``: derives captured/complete/partial/skipped_reasons.

Run directly or via the repo gate:
    python tests/test_snapshots_pure.py
    python -m pytest tests/test_snapshots_pure.py -q -W error
"""

import hashlib
import tempfile
from pathlib import Path

from minicc import snapshots
from minicc.snapshots import SnapshotError, _digest, _relative, _summary
from minicc.snapshots import _SAFE_TASK_ID


# --- _relative: the path-boundary gate --------------------------------------

def test_relative_plain():
    assert _relative("src/app.py") == "src/app.py"


def test_relative_backslash_normalized():
    assert _relative("src\\app.py") == "src/app.py"


def test_relative_nested():
    assert _relative("a/b/c.txt") == "a/b/c.txt"


def test_relative_empty_raises():
    import pytest
    with pytest.raises(SnapshotError):
        _relative("")


def test_relative_none_raises():
    import pytest
    with pytest.raises(SnapshotError):
        _relative(None)


def test_relative_nonstring_raises():
    import pytest
    with pytest.raises(SnapshotError):
        _relative(123)


def test_relative_null_byte_raises():
    import pytest
    with pytest.raises(SnapshotError):
        _relative("a\0b")


def test_relative_drive_raises():
    import pytest
    with pytest.raises(SnapshotError):
        _relative("C:\\windows\\system32.dll")


def test_relative_absolute_raises():
    import pytest
    with pytest.raises(SnapshotError):
        _relative("/etc/passwd")


def test_relative_dotdot_raises():
    import pytest
    with pytest.raises(SnapshotError):
        _relative("../escape")


def test_relative_git_internal_raises():
    import pytest
    with pytest.raises(SnapshotError):
        _relative(".git/secret")


def test_relative_minicc_internal_raises():
    import pytest
    with pytest.raises(SnapshotError):
        _relative(".minicc/x")


def test_relative_embedded_git_allowed():
    # an embedded .git segment is not the root internal prefix -> still allowed
    assert _relative("sub/.git/x") == "sub/.git/x"


# --- _SAFE_TASK_ID: id shape contract ---------------------------------------

def test_safe_task_id_valid():
    assert _SAFE_TASK_ID.fullmatch("Task-1.2_x")
    assert _SAFE_TASK_ID.fullmatch("a")


def test_safe_task_id_rejects_empty_and_long():
    assert not _SAFE_TASK_ID.fullmatch("")
    assert not _SAFE_TASK_ID.fullmatch("a" * 82)


def test_safe_task_id_rejects_slash_and_space():
    assert not _SAFE_TASK_ID.fullmatch("a/b")
    assert not _SAFE_TASK_ID.fullmatch("a b")


# --- _digest: content hashing ----------------------------------------------

def test_digest_of_content():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "f.txt"
        p.write_text("hello", encoding="utf-8")
        assert _digest(p) == hashlib.sha256(b"hello").hexdigest()


def test_digest_missing_is_none():
    assert _digest(Path(tempfile.gettempdir()) / "does-not-exist-xyz") is None


def test_digest_directory_raises():
    import pytest
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(SnapshotError):
            _digest(Path(d))


def test_digest_empty_file():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "empty.bin"
        p.write_bytes(b"")
        assert _digest(p) == hashlib.sha256(b"").hexdigest()


# --- _summary: captured/complete/partial derivation -------------------------

def test_summary_complete_when_no_skipped():
    out = _summary({"task_id": "T1", "files": ["a"], "missing": [], "skipped": []})
    assert out["captured"] is True
    assert out["complete"] is True
    assert out["partial"] is False
    assert out["skipped_reasons"] == {}


def test_summary_partial_when_skipped():
    out = _summary({"task_id": "T1", "files": ["a"], "missing": [], "skipped": ["b"]})
    assert out["captured"] is False
    assert out["complete"] is False
    assert out["partial"] is True


def test_summary_defaults_missing_keys():
    out = _summary({"task_id": "T1"})
    assert out["files"] == []
    assert out["missing"] == []
    assert out["skipped"] == []


def test_summary_preserves_skipped_reasons():
    out = _summary({"task_id": "T1", "skipped_reasons": {"b": "too big"}})
    assert out["skipped_reasons"] == {"b": "too big"}


if __name__ == "__main__":
    import sys
    import pytest

    sys.exit(pytest.main([__file__, "-q", "-W", "error"]))
