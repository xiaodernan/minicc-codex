"""M8-T319: two minicc processes sharing a recent-folder list stop erasing each other.

``WorkspaceCatalog.remember()`` reads the whole catalog, mutates the list in memory
and writes the whole catalog back.  The only thing that made those three steps one
transaction was ``self._lock``, a ``threading.RLock`` - so it spoke to this process
and to nobody else.  ``~/.minicc/workspaces.json`` is the same file for every minicc
process on the machine (``minicc/web.py`` calls ``remember()`` from the service
object's constructor, and the web server, the task worker and the benchmark runner
each build one), so two processes that both wrote successfully still dropped each
other's entries.

Measured on ``dc722d1`` - two child processes, three distinct folders each, a barrier
taken *before* every ``remember()`` so the read-read-write-write interleaving is
forced rather than hoped for, six rounds
(``C:/Users/18414/AppData/Local/Temp/mc-t319/proto_t319.py``):

    VERDICT rounds=6 broken=0 lost_a_side=1 all_six=0 seconds=8.5

Not one of the six rounds kept all six entries; every round kept three.  One round
lost an entire side (``owners={'alpha': 0, 'beta': 3}``), and two rounds also drew
out the M8-T265 belt (``WARNING ... 工作区目录写不回 ... [WinError 5]``) - which is
the other half of why this stayed invisible: the failure was already being caught.

The remedy is the one this repository already uses for a shared checkpoint: hold an
advisory lock on a ``<catalog>.lock`` sidecar across the whole read-modify-write, the
naming rule ``minicc/session.py``:481 uses for session files.

What this does NOT buy:

* ``list()`` still reads without the sidecar.  A reader can miss an entry that lands
  between its read and its render; it cannot see a torn file, because the swap is
  ``os.replace`` and ``test_a_reader_in_another_process_never_sees_a_half_written_catalog``
  in ``tests/test_the_catalog_write_that_a_neighbour_blocks_is_a_warning_not_a_crash.py``
  keeps pinning that.
* The lock is best-effort in both directions.  A neighbour that will not let go costs
  ``_LOCK_ATTEMPTS * _LOCK_RETRY_DELAY``, then writes unlocked anyway, because M8-T265
  established that this path must not raise.  The waiting is the retry loop and not the
  C runtime: measured on this machine the non-blocking Windows mode answers a refusal in
  0.000s while ``LK_LOCK`` parks the caller 9.2s before it admits defeat.
* The in-process ``RLock`` has no witness of its own.  Measured on this plane: an arm
  that drops it and keeps only the sidecar (A6) leaves all eleven cases green, because
  the sidecar excludes a second *handle inside the same process* too - which is the
  very refusal case 4's probe reads.  What the ``RLock`` still buys is that a thread
  queues cheaply instead of charging the two-second ceiling before degrading; that
  difference shows up only under ceiling pressure, and a stopwatch there would be
  measuring this machine rather than the code.
* Nothing here survives a filesystem where byte-range locks are advisory-only.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from minicc.workspaces import WorkspaceCatalog

try:  # Windows
    import msvcrt
except ImportError:  # pragma: no cover - non-Windows
    msvcrt = None  # type: ignore[assignment]

try:  # POSIX
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

REPO = Path(__file__).resolve().parent.parent
CATALOG_NAME = "workspaces.json"
#: The naming rule this file asserts rather than imports: the sidecar is named after
#: the file it protects.  Reading it out of ``minicc/workspaces.py`` would make this
#: door agree with whatever the code happens to do.
LOCK_SUFFIX = ".lock"
LOGGER_NAME = "minicc.workspaces"
#: Tokens the shipped refusal sentence carries, so a reword that drops the diagnosis is
#: a finding and not a silent edit.
LOCK_REFUSAL_TOKENS = ("锁", "占用")

SIDES = ("alpha", "beta")
FOLDERS_PER_SIDE = 3
ROUNDS = 4
CHILD_BUDGET = 90.0
KILL_BUDGET = 30.0
#: One remembered folder per thread-step, so the thread leg has a real count to lose.
THREADS = 4
REMEMBERS_PER_THREAD = 5

CHILD = """
import sys
import time
from pathlib import Path

repo, store, tag, other, folders, steps = sys.argv[1:7]
sys.path.insert(0, repo)
from minicc.workspaces import WorkspaceCatalog

store = Path(store)
steps = int(steps)
catalog = WorkspaceCatalog(path=store / "workspaces.json")


def wait_for(marker: Path, budget: float) -> bool:
    deadline = time.monotonic() + budget
    while not marker.is_file():
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.005)
    return True


for index in range(steps):
    target = Path(folders) / tag / ("folder-%d" % index)
    target.mkdir(parents=True, exist_ok=True)
    Path(store, "%s-%d.ready" % (tag, index)).write_text("ready", encoding="utf-8")
    if not wait_for(Path(store, "%s-%d.ready" % (other, index)), 60.0):
        print("WAIT-FAIL", tag, index)
        raise SystemExit(3)
    catalog.remember(target)
    print("REMEMBERED", tag, index)
print("DONE", tag)
"""


def _catalog_path(root: Path) -> Path:
    return root / CATALOG_NAME


def _sidecar_for(catalog_path: Path) -> Path:
    return catalog_path.with_name(catalog_path.name + LOCK_SUFFIX)


def _workspace(tmp_path: Path, name: str) -> Path:
    target = tmp_path / name
    target.mkdir(parents=True, exist_ok=True)
    return target


def _take_one_byte(handle: Any) -> bool:
    """Try to take one byte of an open sidecar without waiting; ``True`` when it is ours.

    The probe is deliberately the same primitive and the same mode the shipped lock
    uses, so "free here" and "free for ``minicc/workspaces.py``" are one question,
    not two spellings that can drift apart.
    """
    handle.seek(0)
    try:
        if msvcrt is not None:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        elif fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:  # pragma: no cover - no supported platform reaches this
            raise AssertionError("本机没有可用来探测的锁原语")
        return True
    except OSError:
        return False


def _drop_one_byte(handle: Any) -> None:
    """Best-effort unlock; closing the handle is what actually guarantees the drop."""
    try:
        handle.seek(0)
        if msvcrt is not None:
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        elif fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass  # a refused unlock is not a finding while the close below still runs


def _lock_state(lock_path: Path) -> tuple[bool, bool]:
    """Ask the operating system, out of band, whether one byte of ``lock_path`` is free.

    Returns ``(free, existed)``.  Opening the sidecar is how ``minicc/workspaces.py``
    creates it too, so code that never makes one simply reads as "free" - which is the
    honest answer to "is anything protecting this catalog right now".
    """
    existed = lock_path.is_file()
    handle = open(lock_path, "a+")
    try:
        took = _take_one_byte(handle)
        if took:
            _drop_one_byte(handle)
    finally:
        handle.close()
    return took, existed


def _hold_sidecar(lock_path: Path) -> Any:
    """Take the sidecar the way a neighbour process would, and keep holding it.

    Raises if the byte could not be taken, so a leg that reports "the neighbour
    refused us" has first proved the neighbour was in a position to.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+")
    if not _take_one_byte(handle):
        handle.close()
        raise AssertionError(f"锁字节没有被本测试占到，邻居占不住: {lock_path.as_posix()}")
    return handle


def _release_sidecar(handle: Any) -> None:
    try:
        _drop_one_byte(handle)
    finally:
        handle.close()


def _start_child(store: Path, tag: str, other: str, folders: Path) -> subprocess.Popen:
    script = store / f"child_{tag}.py"
    script.write_text(CHILD, encoding="utf-8")
    return subprocess.Popen(
        [
            sys.executable,
            str(script),
            str(REPO),
            str(store),
            tag,
            other,
            str(folders),
            str(FOLDERS_PER_SIDE),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(store),
        # Every path the child touches is an argument; MINICC_HOME is parked inside the
        # round so the child cannot reach this machine's real recent-folder list.
        env=dict(os.environ, PYTHONIOENCODING="utf-8", MINICC_HOME=str(store / "home")),
    )


def _run_race_round(root: Path, index: int) -> dict[str, Any]:
    """One forced interleaving, reported as raw readings - no judgement here."""
    store = root / f"store-{index}"
    store.mkdir(parents=True, exist_ok=True)
    folders = store / f"folders-{index}"
    procs = {
        tag: _start_child(store, tag, other, folders)
        for tag, other in zip(SIDES, (SIDES[1], SIDES[0]))
    }
    reports: dict[str, tuple[int, str, str]] = {}
    for tag, proc in procs.items():
        try:
            stdout, stderr = proc.communicate(timeout=CHILD_BUDGET)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate(timeout=KILL_BUDGET)
            stdout += f"\nTIMEOUT after {CHILD_BUDGET}s"
        reports[tag] = (proc.returncode, stdout, stderr)
    catalog_path = _catalog_path(store)
    payload = json.loads(catalog_path.read_text(encoding="utf-8")) if catalog_path.is_file() else []
    owners = {
        tag: sum(1 for item in payload if f"/{tag}/" in str(item.get("path") or "").replace("\\", "/"))
        for tag in SIDES
    }
    return {
        "index": index,
        "codes": {tag: code for tag, (code, _, _) in reports.items()},
        "stderr": {tag: err for tag, (_, _, err) in reports.items()},
        "stdout": {tag: out for tag, (_, out, _) in reports.items()},
        "entries": len(payload),
        "owners": owners,
    }


@pytest.fixture(scope="module")
def race_rounds(tmp_path_factory: pytest.TempPathFactory) -> list[dict[str, Any]]:
    """The measurement both process cases read, taken once for the module."""
    root = tmp_path_factory.mktemp("race")
    return [_run_race_round(root, index) for index in range(ROUNDS)]


def _describe(rounds: list[dict[str, Any]]) -> str:
    return " | ".join(
        f"round{item['index']}: entries={item['entries']} owners={item['owners']} codes={item['codes']}"
        for item in rounds
    )


# --- the two processes, forced into the interleaving --------------------------


def test_both_sides_of_the_race_keep_every_folder_they_remembered(race_rounds: list[dict[str, Any]]) -> None:
    """Six folders remembered by two processes leave six behind."""
    assert all(code == 0 for item in race_rounds for code in item["codes"].values()), (
        f"a child died, so the counts below would be measuring the harness: {_describe(race_rounds)}\n"
        + "\n".join(item["stderr"][SIDES[0]][-400:] for item in race_rounds)
    )
    due = len(SIDES) * FOLDERS_PER_SIDE
    lost = [item for item in race_rounds if item["entries"] != due]
    assert not lost, (
        f"{len(lost)} of {len(race_rounds)} rounds kept fewer than {due} of {due} entries; "
        f"{_describe(race_rounds)}"
    )


def test_neither_side_of_the_race_loses_its_own_entries(race_rounds: list[dict[str, Any]]) -> None:
    """The count can add up while one whole side is gone, so each side is read."""
    assert all(code == 0 for item in race_rounds for code in item["codes"].values()), (
        f"a child died before it could be counted: {_describe(race_rounds)}"
    )
    gone = [
        (item["index"], tag, count)
        for item in race_rounds
        for tag, count in item["owners"].items()
        if count != FOLDERS_PER_SIDE
    ]
    assert not gone, (
        f"rounds where a side did not keep its own {FOLDERS_PER_SIDE} folders: {gone}; {_describe(race_rounds)}"
    )


# --- where the lock lives, and what it covers ---------------------------------


def test_the_lock_sidecar_is_named_after_the_catalog_it_protects(tmp_path: Path) -> None:
    """One write leaves exactly two files: the catalog and a sidecar named after it."""
    store = tmp_path / "store"
    store.mkdir()
    catalog = WorkspaceCatalog(path=_catalog_path(store))
    catalog.remember(_workspace(tmp_path, "ws"))
    names = sorted(path.name for path in store.iterdir())
    assert names == [CATALOG_NAME, CATALOG_NAME + LOCK_SUFFIX], (
        f"a shared catalog should leave one sidecar that identifies it, saw {names}"
    )
    assert _sidecar_for(_catalog_path(store)).is_file(), "the sidecar the code names is not the one it takes"


def test_the_lock_is_held_across_the_read_and_the_write_not_around_one_of_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The transaction is read *then* write; a lock around either half alone keeps the bug.

    Asked by taking a second handle on the sidecar while each half runs - the operating
    system answers, this file does not read the source for a token.
    """
    store = tmp_path / "store"
    store.mkdir()
    catalog_path = _catalog_path(store)
    catalog = WorkspaceCatalog(path=catalog_path)
    catalog.remember(_workspace(tmp_path, "seed"))
    lock = _sidecar_for(catalog_path)
    readings: dict[str, tuple[bool, bool]] = {}

    real_read, real_write = catalog._read, catalog._write

    def spy_read() -> list[dict[str, Any]]:
        readings["during_read"] = _lock_state(lock)
        return real_read()

    def spy_write(items: list[dict[str, Any]]) -> None:
        readings["during_write"] = _lock_state(lock)
        return real_write(items)

    monkeypatch.setattr(catalog, "_read", spy_read)
    monkeypatch.setattr(catalog, "_write", spy_write)
    catalog.remember(_workspace(tmp_path, "ws"))

    assert readings.keys() == {"during_read", "during_write"}, (
        f"the read or the write was never reached: {sorted(readings)}"
    )
    free = {name: state[0] for name, state in readings.items()}
    assert free == {"during_read": False, "during_write": False}, (
        f"the sidecar was free while the read-modify-write was in progress: {readings} "
        "(free=True means this probe took the byte, i.e. nothing was holding it)"
    )
    assert all(state[1] for state in readings.values()), (
        f"the probe had to create the sidecar itself, so the lock was never armed: {readings}"
    )


def test_the_first_write_to_an_absent_catalog_still_arms_the_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lock cannot be an afterthought bolted onto an existing file."""
    store = tmp_path / "store"
    store.mkdir()
    catalog_path = _catalog_path(store)
    assert not catalog_path.exists(), "this case is about the very first write"
    catalog = WorkspaceCatalog(path=catalog_path)
    lock = _sidecar_for(catalog_path)
    readings: dict[str, tuple[bool, bool]] = {}

    real_read = catalog._read

    def spy_read() -> list[dict[str, Any]]:
        readings["during_first_read"] = _lock_state(lock)
        return real_read()

    monkeypatch.setattr(catalog, "_read", spy_read)
    catalog.remember(_workspace(tmp_path, "ws"))

    assert catalog_path.is_file(), "the first write never landed, so nothing below was measured"
    free, existed = readings["during_first_read"]
    assert not free, (
        "on a catalog that did not exist yet, nothing held the sidecar during the read "
        f"(sidecar present before the probe: {existed})"
    )


def test_the_lock_is_put_back_after_the_write_lands(tmp_path: Path) -> None:
    """A lock nobody releases is a second process waiting out the ceiling per folder."""
    store = tmp_path / "store"
    store.mkdir()
    catalog_path = _catalog_path(store)
    catalog = WorkspaceCatalog(path=catalog_path)
    for name in ("a", "b"):
        catalog.remember(_workspace(tmp_path, name))
    free, existed = _lock_state(_sidecar_for(catalog_path))
    assert existed, "the sidecar the code took is gone - it was never the one named after the catalog"
    assert free, "the sidecar is still held after remember() returned"


# --- a refusal is a diagnosis, not a crash ------------------------------------


def _drive_a_refusal(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> dict[str, Any]:
    """Hold the sidecar as a neighbour would, then run one ``remember()`` through it.

    Returns the target it was asked to remember, the catalog bytes afterwards and the
    shipped logger's warnings.  Raises nothing it does not mean to report: the caller
    decides whether an escaping exception is the finding.
    """
    store = tmp_path / "store"
    store.mkdir()
    catalog_path = _catalog_path(store)
    seed = [{"name": "seed", "path": "/nowhere/seed", "last_opened": 1.0}]
    catalog_path.write_text(json.dumps(seed) + "\n", encoding="utf-8")
    target = _workspace(tmp_path, "ws")
    holder = _hold_sidecar(_sidecar_for(catalog_path))
    try:
        with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
            catalog = WorkspaceCatalog(path=catalog_path)
            catalog.remember(target)
    finally:
        _release_sidecar(holder)
    warnings = [
        record for record in caplog.records if record.name == LOGGER_NAME and record.levelno == logging.WARNING
    ]
    return {
        "catalog_path": catalog_path,
        "target": target,
        "payload": json.loads(catalog_path.read_text(encoding="utf-8")),
        "warnings": warnings,
        "messages": [record.getMessage() for record in warnings],
    }


def test_a_lock_a_neighbour_holds_does_not_take_the_start_path_down(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """M8-T265's rule survives the lock: this path may not raise."""
    errors: list[BaseException] = []
    try:
        _drive_a_refusal(tmp_path, caplog)
    except BaseException as exc:  # recorded, then judged with the exception in view
        errors.append(exc)
    assert not errors, f"a refused cross-process lock escaped as {[type(e).__name__ for e in errors]}: {errors}"


def test_a_refused_lock_still_persists_the_entry(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Degrading must not mean dropping: the folder still reaches the list."""
    report = _drive_a_refusal(tmp_path, caplog)
    paths = [item.get("path") for item in report["payload"]]
    assert report["target"].as_posix() in paths, f"the unlocked fallback wrote nothing back: {paths}"
    assert "/nowhere/seed" in paths, f"the fallback lost the entry it read: {paths}"


def test_a_refused_lock_says_so_and_names_the_catalog(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An operator has to be able to tell 'locked out' from 'nothing to remember'."""
    report = _drive_a_refusal(tmp_path, caplog)
    assert len(report["warnings"]) == 1, (
        f"expected exactly one warning naming the refusal, saw {len(report['warnings'])}: {report['messages']}"
    )
    message = report["messages"][0]
    assert CATALOG_NAME in message, f"the refusal never said which catalog: {message}"
    for token in LOCK_REFUSAL_TOKENS:
        assert token in message, f"the refusal never said the lock was {token}: {message}"


# --- what the fix must not have changed ---------------------------------------


def test_the_recent_list_keeps_its_order_dedup_and_cap_under_the_lock(tmp_path: Path) -> None:
    """Control: the lock sits around the list, it does not decide it."""
    store = tmp_path / "store"
    store.mkdir()
    catalog = WorkspaceCatalog(path=_catalog_path(store), max_items=3)
    for name in ("a", "b", "c", "d"):
        catalog.remember(_workspace(tmp_path, name))
    assert [item["path"] for item in catalog.list()] == [
        _workspace(tmp_path, name).as_posix() for name in ("d", "c", "b")
    ]
    catalog.remember(_workspace(tmp_path, "b"))
    assert [item["path"] for item in catalog.list()] == [
        _workspace(tmp_path, name).as_posix() for name in ("b", "d", "c")
    ]


def test_threads_inside_one_process_lose_nothing(tmp_path: Path) -> None:
    """The axis the old ``RLock`` already covered - kept, because the new code could drop it."""
    store = tmp_path / "store"
    store.mkdir()
    catalog = WorkspaceCatalog(path=_catalog_path(store), max_items=THREADS * REMEMBERS_PER_THREAD)
    failures: list[str] = []

    def worker(tag: str) -> None:
        try:
            for index in range(REMEMBERS_PER_THREAD):
                catalog.remember(_workspace(tmp_path, f"{tag}-folder-{index}"))
        except BaseException as exc:  # a thread that died is not a thread that wrote
            failures.append(f"{tag}: {type(exc).__name__}: {exc}")

    threads = [
        threading.Thread(target=worker, args=(f"t{number}",), name=f"remember-t{number}")
        for number in range(THREADS)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60.0)
        assert not thread.is_alive(), f"{thread.name} was still running after a 60s join"
    assert not failures, failures
    paths = {item["path"] for item in catalog.list()}
    due = THREADS * REMEMBERS_PER_THREAD
    assert len(paths) == due, f"{due} distinct folders remembered across {THREADS} threads, the list holds {len(paths)}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-W", "error"]))
