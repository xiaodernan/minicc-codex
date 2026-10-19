"""M8-T265: a recent-folder write the host blocks is a warning, not a startup crash.

``minicc/workspaces.py`` staged every catalog write under ONE sibling name -
``self.path.with_suffix(".tmp")`` - and left ``mkdir``, ``write_text`` and
``os.replace`` uncontained.  That name is not private: ``workspaces.json`` is the
same file for every minicc process on the machine, so so is its ``.tmp`` sibling.

Measured on ``063c760`` with a neighbour holding that sibling open (plain
``WorkspaceCatalog.remember`` calls, five in a row):

  * all five writes raised ``PermissionError`` and the catalog stayed empty;
  * the neighbour's own staged bytes were replaced by ours first, so the shared
    name did not even identify the content it carried;
  * when the swap refused, the staging file stayed on disk;
  * a catalog under a directory that cannot be made raised ``FileExistsError``.

The reason this is not cosmetic is the call shape: the server's service object
calls ``WorkspaceCatalog()`` and then ``remember(workspace)`` from its
constructor with no handler, and that constructor is what the web server start,
the task worker and the benchmark runner all build.  One process holding a
guessable name can make a second one refuse to start.

The remedy is what the rest of this repository already does for staged writes:
pick a staging name that only this write owns, treat the whole swap as
best-effort, and say so in the log when the host refuses.  Losing a recent-folder
entry is a cosmetic failure; killing a server start is not.

What this does NOT claim: the catalog is still read-modify-write with no lock, so
two processes that both succeed can still drop each other's entries (measured on
both faces: 20 remembers per process left ``entries=12 alpha=12 beta=0``).  The
half-written-file property belongs to ``os.replace`` and is only re-pinned here by
the reader control below, not bought by this fix.
"""

from __future__ import annotations

import errno
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from minicc.workspaces import WorkspaceCatalog

CATALOG_NAME = "workspaces.json"
#: The name the shipped code used to stage under - public, because it is derived
#: from the catalog's own name and therefore the same in every process.
SHARED_STAGING_NAME = "workspaces.tmp"
LOGGER_NAME = "minicc.workspaces"
NEIGHBOUR_TOKEN = "另一台进程暂存的内容"

HOLDER_CHILD = '''
import sys
from pathlib import Path

held, ready, token = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
handle = open(held, "r", encoding="utf-8")
ready.write_text("held\\n", encoding="utf-8")
sys.stdin.buffer.read()
try:
    later = held.read_text(encoding="utf-8")
except OSError as exc:
    later = "<gone %s>" % type(exc).__name__
handle.close()
print("INTACT=%s" % str(later.startswith(token)).lower())
'''

READER_CHILD = '''
import json
import sys
from pathlib import Path

catalog, ready, stop = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
counts = {"ok": 0, "partial": 0, "missing": 0, "blocked": 0}
ready.write_text("reading\\n", encoding="utf-8")
while not stop.exists():
    try:
        payload = json.loads(catalog.read_text(encoding="utf-8"))
    except FileNotFoundError:
        counts["missing"] += 1
    except PermissionError:
        counts["blocked"] += 1
    except (json.JSONDecodeError, UnicodeDecodeError):
        counts["partial"] += 1
    else:
        counts["ok"] += 1 if isinstance(payload, list) else 0
        counts["partial"] += 0 if isinstance(payload, list) else 1
print(json.dumps(counts))
'''


def _catalog(root: Path) -> WorkspaceCatalog:
    return WorkspaceCatalog(path=root / CATALOG_NAME)


def _workspace(root: Path, name: str) -> Path:
    target = root / name
    target.mkdir(parents=True, exist_ok=True)
    return target


def _seed(root: Path, entries: int = 0) -> Path:
    """A catalog file with a known, complete list already in it."""
    root.mkdir(parents=True, exist_ok=True)
    catalog = root / CATALOG_NAME
    payload = [{"name": f"old{i}", "path": f"/nowhere{i}", "last_opened": 1.0} for i in range(entries)]
    catalog.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    return catalog


def _start_child(tmp_path: Path, source: str, args: list[str]) -> subprocess.Popen:
    script = tmp_path / f"child_{abs(hash(source))}_{len(args)}.py"
    script.write_text(source, encoding="utf-8")
    return subprocess.Popen(
        [sys.executable, str(script), *[str(a) for a in args]],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(tmp_path),
    )


def _wait_for_marker(marker: Path, proc: subprocess.Popen, what: str, budget: float = 30.0) -> None:
    """Poll the fact the child publishes, with a declared budget and a verdict."""
    deadline = time.monotonic() + budget
    while not marker.is_file():
        code = proc.poll()
        if code is not None:
            raise AssertionError(f"{what}: the child exited rc={code} before writing {marker.name}")
        if time.monotonic() >= deadline:
            raise AssertionError(f"{what}: no {marker.name} within {budget}s")
        time.sleep(0.02)


def _stop(proc: subprocess.Popen, budget: float = 30.0) -> str:
    stdout, stderr = proc.communicate(timeout=budget)
    assert proc.returncode == 0, f"child exited {proc.returncode}: {(stderr or '').strip()[-200:]}"
    return (stdout or "").strip()


def test_a_neighbour_holding_the_predictable_staging_name_does_not_stop_the_write(
    tmp_path: Path,
) -> None:
    """A sibling another process holds is not our business."""
    catalog_path = _seed(tmp_path)
    staged = tmp_path / SHARED_STAGING_NAME
    staged.write_text(NEIGHBOUR_TOKEN + "\n", encoding="utf-8")
    holder = open(staged, "r", encoding="utf-8")  # noqa: SIM115 - holding it IS the scenario
    catalog = _catalog(tmp_path)
    errors: list[BaseException] = []
    try:
        for index in range(5):
            try:
                catalog.remember(_workspace(tmp_path, f"ws{index}"))
            except BaseException as exc:  # recorded, then judged below with the count in view
                errors.append(exc)
    finally:
        holder.close()
    assert not errors, f"5 remembers raised: {[type(e).__name__ for e in errors]}"
    assert len(catalog.list()) == 5
    assert staged.read_text(encoding="utf-8").startswith(NEIGHBOUR_TOKEN), (
        "our write went through the neighbour's staging file"
    )


def test_a_second_process_holding_that_name_does_not_stop_the_write(tmp_path: Path) -> None:
    """The same neighbour as another process, which is how it happens in practice."""
    catalog_path = _seed(tmp_path)
    staged = tmp_path / SHARED_STAGING_NAME
    staged.write_text(NEIGHBOUR_TOKEN + "\n", encoding="utf-8")
    ready = tmp_path / "holder-ready.txt"
    proc = _start_child(tmp_path, HOLDER_CHILD, [staged, ready, NEIGHBOUR_TOKEN])
    try:
        _wait_for_marker(ready, proc, "the holder attached to the staging file")
        catalog = _catalog(tmp_path)
        for index in range(5):
            catalog.remember(_workspace(tmp_path, f"ws{index}"))
    finally:
        assert proc.stdin is not None
        proc.stdin.close()
        report = _stop(proc)
    assert "INTACT=true" in report, f"the neighbour lost its own staged bytes: {report}"
    assert len(catalog.list()) == 5


def test_a_refused_swap_leaves_no_staging_file_behind(tmp_path: Path, monkeypatch) -> None:
    """When the host says no, nothing of ours may stay where the next writer looks."""
    catalog_path = _seed(tmp_path, entries=2)
    before = catalog_path.read_text(encoding="utf-8")
    monkeypatch.setattr(
        os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError(errno.EACCES, "模拟拒绝"))
    )
    catalog = _catalog(tmp_path)
    catalog.remember(_workspace(tmp_path, "ws"))
    leftovers = sorted(p.name for p in tmp_path.glob("*.tmp"))
    assert not leftovers, f"staging files outlived the refusal: {leftovers}"
    assert catalog_path.read_text(encoding="utf-8") == before, (
        "the refusal rewrote the catalog it could not replace"
    )
    assert len(catalog.list()) == 2


def test_a_parent_the_host_cannot_create_is_a_warning_not_an_error(tmp_path: Path) -> None:
    """A catalog path under a regular file cannot be made - and must not raise here."""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory\n", encoding="utf-8")
    catalog = WorkspaceCatalog(path=blocker / "nested" / CATALOG_NAME)
    for index in range(3):
        catalog.remember(_workspace(tmp_path, f"ws{index}"))
    assert blocker.is_file() and not blocker.is_dir()
    assert catalog.list() == []


def test_the_warning_names_the_catalog_and_the_reason_the_host_refused(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    """Silence is the other half of the defect: an operator must learn it went wrong."""
    catalog_path = _seed(tmp_path, entries=1)
    reason = "模拟拒绝"
    monkeypatch.setattr(
        os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError(errno.EACCES, reason))
    )
    catalog = _catalog(tmp_path)
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        catalog.remember(_workspace(tmp_path, "ws"))
    warnings = [r for r in caplog.records if r.name == LOGGER_NAME and r.levelno == logging.WARNING]
    assert len(warnings) == 1, f"expected one warning from {LOGGER_NAME}, got {len(warnings)}"
    message = warnings[0].getMessage()
    assert CATALOG_NAME in message, f"the refusal never said which file: {message}"
    assert catalog_path.name in message
    assert reason in message, f"the refusal never said why: {message}"


def test_two_writes_stage_under_two_names_the_neighbour_cannot_guess(
    tmp_path: Path, monkeypatch
) -> None:
    """Uniqueness asked of the swap itself, not of a spelling in the source."""
    _seed(tmp_path)
    swaps: list[tuple[str, str]] = []
    real = os.replace

    def spy(src, dst, *args, **kwargs):
        swaps.append((str(src), str(dst)))
        return real(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", spy)
    catalog = _catalog(tmp_path)
    for index in range(3):
        catalog.remember(_workspace(tmp_path, f"ws{index}"))
    assert len(swaps) == 3, f"three writes, {len(swaps)} swaps - the write never landed"
    sources = [src for src, _ in swaps]
    assert len(set(sources)) == 3, f"two writes shared one staging name: {sources}"
    assert len({dst for _, dst in swaps}) == 1, f"the swaps left one catalog: {swaps}"


def test_a_reader_in_another_process_never_sees_a_half_written_catalog(tmp_path: Path) -> None:
    """Control: the atomic swap is the property the reader relies on, and it stays."""
    catalog_path = _seed(tmp_path)
    ready = tmp_path / "reader-ready.txt"
    stop = tmp_path / "reader-stop.txt"
    proc = _start_child(tmp_path, READER_CHILD, [catalog_path, ready, stop])
    catalog = _catalog(tmp_path)
    _wait_for_marker(ready, proc, "the reader attached to the catalog")
    for index in range(20):
        catalog.remember(_workspace(tmp_path, f"ws{index}"))
    stop.write_text("stop\n", encoding="utf-8")
    report = _stop(proc)
    counts = json.loads(report)
    assert counts["partial"] == 0, f"a reader saw a torn catalog: {report}"
    assert counts["ok"] >= 1, f"the reader never read a complete catalog: {report}"
    total = sum(counts.values())
    assert total >= 50, f"the reader barely looked: {report}"


def test_the_recent_list_keeps_its_order_dedup_and_cap(tmp_path: Path) -> None:
    """Control: containment must not have quietly changed what the list says."""
    catalog = WorkspaceCatalog(path=tmp_path / CATALOG_NAME, max_items=2)
    for name in ("a", "b", "c"):
        catalog.remember(_workspace(tmp_path, name))
    assert [item["path"] for item in catalog.list()] == [
        _workspace(tmp_path, "c").as_posix(),
        _workspace(tmp_path, "b").as_posix(),
    ]
    catalog.remember(_workspace(tmp_path, "c"))
    assert len(catalog.list()) == 2
    assert catalog.list()[0]["exists"] is True


def test_the_swap_really_lands_the_new_list_on_the_destination(tmp_path: Path) -> None:
    """The belt may swallow a refusal, but it may not swallow the write."""
    catalog_path = _seed(tmp_path)
    catalog = _catalog(tmp_path)
    target = _workspace(tmp_path, "ws")
    catalog.remember(target)
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert [item["path"] for item in payload] == [target.as_posix()]


def test_a_failure_that_is_not_a_sharing_violation_still_escapes(tmp_path: Path, monkeypatch) -> None:
    """The belt is ``OSError``-only: a real bug must not be logged away as a refusal."""
    _seed(tmp_path)

    def broken(*args, **kwargs):
        raise RuntimeError("不是共享冲突的缺陷")

    monkeypatch.setattr(json, "dumps", broken)
    catalog = _catalog(tmp_path)
    with pytest.raises(RuntimeError):
        catalog.remember(_workspace(tmp_path, "ws"))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-W", "error"]))
