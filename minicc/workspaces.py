"""A tiny persistent catalog of local folders used by the web workspace."""

from __future__ import annotations

import contextlib
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import IO, Any, Iterator

from .atomic_file import read_text_with_retry, replace_with_retry
from .config import home_dir
from .logging_setup import get_logger

try:  # Windows
    import msvcrt
except ImportError:  # pragma: no cover - non-Windows
    msvcrt = None  # type: ignore[assignment]

try:  # POSIX
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

LOG = get_logger("workspaces")

#: ``remember()`` reads the whole catalog, mutates it in memory and writes the
#: whole catalog back.  The file is the same one for every minicc process on the
#: machine, so two processes that each succeed still drop each other's entries:
#: measured on ``dc722d1`` with two barrier-synchronised children doing three
#: remembers each, 0 of 6 rounds kept all six entries and one round lost a whole
#: side.  The in-process ``RLock`` was never the answer for that.
#:
#: The ceiling below bounds the *waiting*, not the correctness.  A neighbour that
#: will not let go costs two seconds and then degrades to the unlocked write,
#: because M8-T265 already established that this path must not raise: losing a
#: recent folder is cosmetic, refusing to start a web server is not.
_LOCK_ATTEMPTS = 40
_LOCK_RETRY_DELAY = 0.05
_LOCK_BYTES = 1


def _lock_path_for(catalog_path: Path) -> Path:
    """The sidecar protecting one catalog - the naming rule ``minicc/session.py`` uses too."""
    return catalog_path.with_name(catalog_path.name + ".lock")


def _acquire(lock_path: Path) -> tuple[IO[str] | None, OSError | None]:
    """Open ``lock_path`` and take it.  Returns (handle, refusal); one of them is None.

    ``LK_NBLCK`` is the mode this loop needs: measured against a neighbour process
    holding one byte, ``LK_LOCK`` parks the caller for 9.2s before it admits defeat
    with EDEADLOCK, while ``LK_NBLCK`` answers in 0.000s.  Retrying the immediate
    answer is what keeps the ceiling below honest.
    """
    if msvcrt is None and fcntl is None:
        return None, OSError("本机没有可用的跨进程锁原语（msvcrt 与 fcntl 均未导出）")
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(lock_path, "a+")
    except OSError as exc:
        return None, exc
    try:
        for attempt in range(_LOCK_ATTEMPTS):
            try:
                handle.seek(0)
                if msvcrt is not None:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, _LOCK_BYTES)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return handle, None
            except OSError as exc:
                if attempt == _LOCK_ATTEMPTS - 1:
                    raise exc
                time.sleep(_LOCK_RETRY_DELAY)
        raise OSError(f"锁重试循环走完 {_LOCK_ATTEMPTS} 次却没有判决")
    except OSError as exc:
        handle.close()
        return None, exc


def _release(handle: IO[str]) -> None:
    """Put the lock back.  A refusal here is not fatal: closing the handle drops it."""
    try:
        handle.seek(0)
        if msvcrt is not None:
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, _LOCK_BYTES)
        elif fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        LOG.warning(f"工作区目录锁解不开，交给关闭句柄释放 {handle.name}：{exc}")
    finally:
        handle.close()


@contextlib.contextmanager
def _advisory_lock(catalog_path: Path) -> Iterator[bool]:
    """Hold the catalog's sidecar across one read-modify-write, or say why not.

    Yields whether the lock is actually held.  It never raises: a busy or
    unmakeable sidecar degrades to the unlocked write plus one WARNING naming the
    catalog, which is today's behaviour with a diagnosis attached.
    """
    handle, refusal = _acquire(_lock_path_for(catalog_path))
    if refusal is not None:
        LOG.warning(
            f"工作区目录锁被其他进程占用，本次不带跨进程锁写入 {catalog_path.as_posix()}：{refusal}"
        )
    try:
        yield refusal is None
    finally:
        if handle is not None:
            _release(handle)


def resolve_workspace_path(
    raw: object,
    *,
    roots: tuple[object, ...] | list[object] | None = None,
    default: Path | None = None,
) -> Path:
    """Single gate for every workspace entry point (M2-T1).

    Resolves ``raw`` (or ``default`` when empty), requires an existing
    directory, and enforces ``workspace_roots`` when non-empty. All five
    entries — switch_workspace, RPC, /api/chat, task submit, snapshot
    restore — must call this so ``workspace_roots=(A,)`` cannot be
    bypassed with B.
    """
    text = str(raw or "").strip()
    if not text:
        if default is None:
            raise ValueError("工作区路径不能为空")
        candidate = default.expanduser().resolve()
    else:
        candidate = Path(text).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        candidate = candidate.resolve()
    if not candidate.is_dir():
        raise ValueError(f"工作区不是有效目录: {candidate}")
    allowed = [Path(r).expanduser().resolve() for r in (roots or ()) if str(r or "").strip()]
    if allowed and not any(
        candidate == root or candidate.is_relative_to(root) for root in allowed
    ):
        shown = ", ".join(r.as_posix() for r in allowed)
        raise ValueError(
            f"工作区不在允许的目录白名单内: {candidate.as_posix()}（允许: {shown}）"
        )
    return candidate


class WorkspaceCatalog:
    """Remember recently opened folders without storing model credentials."""

    def __init__(self, path: Path | None = None, max_items: int = 12) -> None:
        self.path = path or home_dir() / "workspaces.json"
        self.max_items = max(1, max_items)
        self._lock = threading.RLock()

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            items = self._read()
        output: list[dict[str, Any]] = []
        for item in items:
            raw_path = str(item.get("path") or "")
            if not raw_path:
                continue
            candidate = Path(raw_path)
            output.append(
                {
                    "name": str(item.get("name") or candidate.name or raw_path),
                    "path": raw_path,
                    "exists": candidate.is_dir(),
                    "last_opened": item.get("last_opened"),
                }
            )
        return output

    def remember(self, path: Path) -> None:
        candidate = path.expanduser().resolve()
        record = {
            "name": candidate.name or str(candidate),
            "path": candidate.as_posix(),
            "last_opened": time.time(),
        }
        # The thread lock keeps two threads of this process out of each other's
        # read-modify-write; only the sidecar says the same thing to the *next*
        # minicc process, and it has to stay taken from the read through the
        # swap - a lock around either half alone leaves the lost update in place.
        with self._lock, _advisory_lock(self.path):
            items = [
                item
                for item in self._read()
                if str(item.get("path") or "").lower() != record["path"].lower()
            ]
            items.insert(0, record)
            self._write(items[: self.max_items])

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        try:
            # M8-T523: a reader that is mid-read makes the writer's swap fail
            # with WinError 5, and a reader that IS refused used to answer
            # "the catalog is empty" - which is a wrong answer, not a
            # degraded one.  Riding the window out costs a few milliseconds
            # and keeps the list the user actually has.
            payload = json.loads(read_text_with_retry(self.path, attempts=8, delay=0.005))
        except (OSError, ValueError):
            # M8-T277: ValueError covers both decode failures.  A catalog
            # that is not UTF-8 used to raise a bare UnicodeDecodeError out
            # of here, past the silent-degradation this method promises.
            return []
        return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []

    def _write(self, items: list[dict[str, Any]]) -> None:
        """Stage under a name only this write owns, then swap it in as one file.

        workspaces.json is shared by every minicc process on the machine, so a sibling
        named once (``workspaces.tmp``) is a second writer's target too: Windows refuses
        the swap with WinError 32 while that neighbour holds the staging file and WinError 5
        while it holds the destination - both measured.  Losing a recent-folder entry is a
        cosmetic failure; refusing to start a second web server over one is not, so the
        write is best-effort and says where it went, and the staging file never outlives it.

        M8-T523: the refusal is *transient* - the reader that caused it holds the
        destination for microseconds - so the swap is ridden out (the
        repository's one answer, ``minicc/atomic_file.py``) before the write is
        given up on.  Before that, one refused swap silently dropped the write.
        """
        temporary = self.path.parent / f"{self.path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            replace_with_retry(temporary, self.path, attempts=8, delay=0.005)
        except OSError as exc:
            LOG.warning(f"工作区目录写不回 {self.path.as_posix()}：{exc}")
            try:
                temporary.unlink()
            except OSError:
                pass


__all__ = ["WorkspaceCatalog", "resolve_workspace_path"]
