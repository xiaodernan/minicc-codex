"""Regression tests for PROJECT_REVIEW P1#2 (retrieval budget).

P1#2: local retrieval used to let hidden directories (and dependency caches)
consume the walk budget, so a project full of ``.cache``/``.venv``/
``node_modules`` trees could exhaust ``max_directories`` before any source
file was seen. The fix prunes those directories *before descent* (it rewrites
``dirs[:]`` to drop any name starting with ``.`` and any name in ``SKIP_DIRS``),
so they never count toward the budget and never appear in the collected set.

These tests lock that behaviour in:

* a file inside a hidden directory is never collected;
* a file inside any ``SKIP_DIRS`` entry is never collected;
* a deep hidden tree does not starve a tight directory budget, so a visible
  source file is still indexed.

To confirm they are real regression tests, the third test is constructed so
that, *without* the ``not name.startswith(".")`` pruning, ``os.walk`` would
descend into the hidden tree first (dot names sort before letters) and hit the
budget before ever yielding the visible ``src`` directory.
"""

from __future__ import annotations

from pathlib import Path

from minicc.agent.retrieval import SKIP_DIRS, LocalEvidenceIndex


def _write(path: Path, text: str = "x = 1\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _collected_rels(root: Path, **kwargs: object) -> set[str]:
    index = LocalEvidenceIndex(root, **kwargs)  # type: ignore[arg-type]
    return {rel for _path, rel in index._files()}


def test_hidden_directory_is_not_walked(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "app.py")
    _write(tmp_path / ".secret" / "leak.py")
    rels = _collected_rels(tmp_path)
    assert "src/app.py" in rels
    assert not any(r.startswith(".secret/") for r in rels), rels


def test_skip_dirs_are_pruned(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "app.py")
    for skip in ("node_modules", ".venv", ".git", "__pycache__"):
        _write(tmp_path / skip / "lib.py")
    rels = _collected_rels(tmp_path)
    assert "src/app.py" in rels
    for skip in ("node_modules", ".venv", ".git", "__pycache__"):
        assert not any(r.startswith(skip + "/") for r in rels), (skip, rels)


def test_hidden_tree_does_not_consume_directory_budget(tmp_path: Path) -> None:
    # One visible source file, plus a deep hidden tree that would blow a tiny
    # directory budget if its levels were ever counted.
    _write(tmp_path / "src" / "app.py")
    current = tmp_path / ".cache"
    for i in range(10):
        current = current / f"level{i}"
        _write(current / "junk.py")
    # Tight budget: only a handful of directories may be walked.
    rels = _collected_rels(tmp_path, max_directories=3)
    assert "src/app.py" in rels, rels
    assert not any(r.startswith(".cache/") for r in rels), rels


def test_skip_dirs_constant_keeps_known_dependency_caches(tmp_path: Path) -> None:
    # Guard the constant itself: if a future edit drops a known cache dir from
    # SKIP_DIRS, this names the regression immediately.
    for expected in ("node_modules", ".venv", ".git", "__pycache__"):
        assert expected in SKIP_DIRS, expected
