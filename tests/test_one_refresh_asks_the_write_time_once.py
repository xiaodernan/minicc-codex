"""One refresh asks "when was this file written" twice, and the second answer wins.

``LocalEvidenceIndex._refresh`` stats every candidate for its cache signature
(``minicc/agent/retrieval.py:509``, keyed at ``:533``) and then, after the body has
been read, ``_build_record`` stats **the same file again** for ``record.mtime``
(``:615``, stored at ``:628``).  One refresh therefore holds two answers to one
question, and only one of them is the number the memo is built from.

Measured on this machine before the change (`scratch/probe_533.txt`, `probe_533b.txt`):

* a cold build of 200 files reads ``Path.stat`` 5.015 times per indexed file, a warm
  refresh of the same tree 4.010 - the difference is exactly the second question,
  one syscall per rebuilt file;
* attributed by caller over a 1000-file tree: ``permissions.py:load_permission_rules``
  2.000 per file (queued as M8-T537), ``retrieval.py:_refresh`` 1.000,
  ``retrieval.py:_build_record`` **1.000**, pathlib's own ``lstat`` 1.102;
* when that second stat is made to fail, the record survives with ``mtime == 0.0``:
  a brand-new file is then scored as ``age_days = 20,755`` and its freshness bonus
  reads ``1.65e-208``, while the census still says ``files_skipped 0`` - so a failed
  read is answered with an invented value, not with "unknown";
* when the file is written between the two questions, the cache key keeps the older
  answer and the age keeps the newer one - measured 3000.0s apart, and because the
  scorer clamps the age with ``max(0.0, ...)`` (`:364`) a body that has already gone
  stale reads as brand-new and collects the full ``W_FRESHNESS`` of 3.0.

The fix has one shape: the mtime **is** the signature's ``st_mtime``.  One question,
one answer, and the branch that invented an epoch loses its input.
"""

from __future__ import annotations

import os
import sys
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from minicc.agent.retrieval import LocalEvidenceIndex

FILES = 6


@contextmanager
def attributed_stats():
    """Count every ``Path.stat`` under the function that asked for it.

    "the second stat of a file" is not a usable handle: the tree is stat'd while it
    is collected as well, and a probe that guessed by order dropped the file out of
    the index instead of reaching the site under study (measured).  The caller's own
    frame name is the handle.
    """
    counts: Counter = Counter()
    original = Path.stat

    def counted(self, **kwargs):
        counts[sys._getframe(1).f_code.co_name] += 1
        return original(self, **kwargs)

    Path.stat = counted  # type: ignore[method-assign]
    try:
        yield counts
    finally:
        Path.stat = original  # type: ignore[method-assign]
        assert Path.stat is original, "the counter leaked a patch"


@contextmanager
def failing_build_stats():
    """Make only ``_build_record``'s own stat raise, the way a file that vanished
    between the signature and the age does."""
    fired: list[str] = []
    original = Path.stat

    def raising(self, **kwargs):
        if sys._getframe(1).f_code.co_name == "_build_record":
            fired.append(str(self))
            raise FileNotFoundError(2, "No such file or directory", str(self))
        return original(self, **kwargs)

    Path.stat = raising  # type: ignore[method-assign]
    try:
        yield fired
    finally:
        Path.stat = original  # type: ignore[method-assign]
        assert Path.stat is original, "the patch leaked"


def _tree(root: Path) -> list[Path]:
    root.mkdir(parents=True, exist_ok=True)
    created = []
    for i in range(FILES):
        path = root / f"mod_{i}.py"
        path.write_text(f"def handler_{i}(payload):\n    return payload\n", encoding="utf-8")
        created.append(path)
    return created


def test_the_refresh_is_the_only_reader_of_the_write_time(tmp_path: Path) -> None:
    """The body builder must not ask the question the caller already asked."""
    files = _tree(tmp_path / "ws")
    with attributed_stats() as counts:
        index = LocalEvidenceIndex(files[0].parent, max_files=100)
        census = index.stats()
    assert int(census["files_indexed"]) == FILES, census
    assert int(census["files_rebuilt"]) == FILES, census
    assert counts["_build_record"] == 0, (
        f"_build_record asked for the write time {counts['_build_record']} times; "
        "the refresh already stat'd every one of these files for its cache signature, "
        "so every one of those is a second answer to the same question"
    )
    assert counts["_refresh"] == FILES, (
        f"the refresh asked {counts['_refresh']} times for {FILES} files: exactly one "
        "per rebuilt file is the denominator this leg is about - zero means the walk "
        "stopped and the gate is green because nothing was indexed, more than one "
        "means the second question moved here instead of disappearing"
    )


def test_the_age_and_the_cache_key_are_the_same_answer(tmp_path: Path) -> None:
    """One file, one refresh, one answer to "when was this written"."""
    files = _tree(tmp_path / "ws")
    victim = files[0]
    original_open = Path.open

    def edit_after_read(self, *args, **kwargs):
        stream = original_open(self, *args, **kwargs)
        if self != victim:
            return stream
        real_read = stream.read
        state = {"done": False}

        def read(*rargs, **rkwargs):
            body = real_read(*rargs, **rkwargs)
            if not state["done"]:
                state["done"] = True
                # the file is written again right after the index has taken its body
                os.utime(victim, ns=(os.stat(victim).st_atime_ns, int((time.time() + 3000.0) * 1e9)))
            return body

        stream.read = read  # type: ignore[method-assign]
        return stream

    Path.open = edit_after_read  # type: ignore[method-assign]
    try:
        index = LocalEvidenceIndex(victim.parent, max_files=100)
        index.stats()
    finally:
        Path.open = original_open  # type: ignore[method-assign]

    rel = victim.name
    record = next(record for record in index._records if record.rel == rel)
    signature = index._record_cache[rel][0]
    assert abs(record.mtime - signature[1] / 1e9) < 1.0, (
        f"the cache key says {signature[1] / 1e9:.1f} and the age says {record.mtime:.1f}: "
        "the memo and the score are reading two different answers about one file, and "
        "the scorer clamps the newer one to a zero-day age, so a body that just went "
        "stale collects the full freshness bonus"
    )


def test_a_vanishing_body_does_not_invent_an_age(tmp_path: Path) -> None:
    """A write time that cannot be read is not the year 1970."""
    _tree(tmp_path / "ws")
    with failing_build_stats() as fired:
        index = LocalEvidenceIndex(tmp_path / "ws", max_files=100)
        census = index.stats()
    invented = [record.rel for record in index._records if record.mtime == 0.0]
    assert not invented, (
        f"these records carry an invented epoch: {', '.join(invented)}; the census "
        f"says files_skipped {census['files_skipped']}, so nothing reports that a "
        "read failed - the failure was answered with a number instead of a gap"
    )
    assert not fired, (
        "green because the body builder no longer asks, which is the point - but the "
        "leg has to say so: if this ever fires while `invented` stays empty, the "
        "fabrication moved rather than disappeared"
    )


def test_the_age_is_the_write_time_and_not_the_creation_time(tmp_path: Path) -> None:
    """Reusing the signature's ``stat`` is only right if it reads the **mtime** field.

    An implementation that takes the same object and the wrong field keeps every
    count at zero and every key matching, so the legs above would stay green while
    the score decayed off a timestamp the file has never carried.
    """
    files = _tree(tmp_path / "ws")
    victim = files[0]
    stamp = victim.stat()
    moved = int((time.time() + 3000.0) * 1e9)
    os.utime(victim, ns=(stamp.st_atime_ns, moved))
    index = LocalEvidenceIndex(victim.parent, max_files=100)
    assert int(index.stats()["files_indexed"]) == FILES
    record = next(r for r in index._records if r.rel == victim.name)
    assert abs(record.mtime - moved / 1e9) < 1.0, (
        f"the age reads {record.mtime:.1f} while the file's own mtime is "
        f"{moved / 1e9:.1f}: the reuse took a different field out of the same stat"
    )


def test_the_indexed_bodies_all_carry_a_real_age(tmp_path: Path) -> None:
    """Anti-vacuity for the leg above: the tree really was indexed."""
    files = _tree(tmp_path / "ws")
    index = LocalEvidenceIndex(files[0].parent, max_files=100)
    census = index.stats()
    assert int(census["files_indexed"]) == FILES, census
    assert len(index._records) == FILES
    now = time.time()
    assert all(0.0 < record.mtime <= now + 1.0 for record in index._records), [
        (record.rel, record.mtime) for record in index._records
    ]
