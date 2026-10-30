"""M8-T533 — the record is built from the signature the refresh already took.

The index walks every file, stats it once, keys its memo by that signature and
then read the body.  ``_build_record`` used to stat the file **again** after
the read for its ``mtime`` field: one extra syscall per file, and a TOCTOU -
a file that changed between the two stats got a signature from before the
read paired with content from after it.

The record now takes the caller's stat.  These cases pin both halves: the
builder never asks for a stat, and the refresh hands it the same object it
keys the memo with.
"""

from __future__ import annotations

from pathlib import Path

from minicc.agent.retrieval import LocalEvidenceIndex


class _HandedStat:
    """The two attributes the builder reads, without touching the disk."""

    st_mtime = 1234.5
    st_ino = 11
    st_mtime_ns = 2_000_000_000
    st_ctime_ns = 3_000_000_000
    st_size = 7


def test_the_builder_does_not_ask_the_filesystem_for_a_second_stat(
    tmp_path: Path, monkeypatch,
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    body = workspace / "a.py"
    body.write_text("x = 1\n", encoding="utf-8")
    index = LocalEvidenceIndex(workspace)

    # Count stats of *this* file only: pytest and pathlib may stat freely
    # around a failing test, and a probe that raises on every stat tears the
    # reporter down instead of reddening an assertion.
    seen = {"stat": 0}
    original = Path.stat

    def counted(self, *args, **kwargs):
        if self == body:
            seen["stat"] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", counted)
    record = index._build_record(body, "a.py", _HandedStat())

    assert record is not None
    assert seen["stat"] == 0, "_build_record asked for a stat it was handed"
    assert record.mtime == _HandedStat.st_mtime, record.mtime


def test_the_refresh_hands_the_signature_it_keys_the_memo_with(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "a.py").write_text("x = 1\n", encoding="utf-8")
    index = LocalEvidenceIndex(workspace, refresh_interval=0.0)

    handed: dict[str, object] = {}
    original = index._build_record

    def spy(path: Path, rel: str, stat):
        handed[rel] = stat
        return original(path, rel, stat)

    index._build_record = spy  # type: ignore[method-assign]
    index.refresh()

    stat = handed["a.py"]
    assert index._record_cache["a.py"][0] == (
        stat.st_ino, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size
    ), "the memo key and the record came from two different stats"