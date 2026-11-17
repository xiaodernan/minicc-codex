"""M8-T1129 — the allowlist is one file for every minicc process in a workspace.

``.minicc/allowlist.json`` holds the user's *consent*: the per-session rules
for which commands, paths and tools a session may use. ``replace_session_rules``
is a read-modify-write of that file, and until this batch it was guarded by a
``threading.RLock`` — a lock that speaks to this process and to nobody else.
Two minicc processes in the same workspace could each read the old content,
each merge their own rule, and each write it back: the second write silently
drops the first session's rule. Measured on the plane that found this (two
children forced into the same critical section, eight rounds): **0 of 8**
rounds kept both sessions, and every round kept exactly one.

The fix is the repository's one answer for this
(``minicc/sidecar_lock.py``), held across the read *and* the write — a lock
around the write alone still lets two processes read the same old content.
A refused lock is **not** downgraded to an unlocked write, for the same reason
a session checkpoint raises: this file holds consent, and a lost rule is a
session silently running without one.

This gate pins the shape, not the measurement:

* A neighbour that holds the sidecar makes the replacement **fail**, the file
  on disk is **unchanged**, and the read inside the read-modify-write never
  happens (the lock covers both halves, not just the write).
* The refusal **names the file** and the ceiling the outcome derivation can
  stand behind — never a retyped constant.
* With no neighbour, the replacement lands exactly as before.
* The sidecar is named after the allowlist, like every other protected file.

Blind spots, written down:

* The sidecar is advisory: it keeps cooperating minicc processes out of each
  other's read-modify-write; it does nothing at all against a process that
  ignores it.
* These legs run on the host runner (Windows, msvcrt); the POSIX side is the
  same question asked through fcntl and is not proved by a Windows run.
* This gate does not prove two *concurrent subprocesses* keep each other's
  rules — that is what the interleaving measurement on the finding plane
  showed (0/8 before, 6/6 after the same mechanism elsewhere); here we pin
  the deterministic shape: held sidecar ⇒ refused, untouched file, no read.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import minicc.allowlist as al
from minicc.sidecar_lock import LOCK_SUFFIX, sidecar_path_for

try:  # Windows
    import msvcrt
except ImportError:  # pragma: no cover - non-Windows
    msvcrt = None  # type: ignore[assignment]

try:  # POSIX
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]


def _allowlist_path(workspace: Path) -> Path:
    return workspace / ".minicc" / "allowlist.json"


def _produce_original(workspace: Path) -> None:
    workspace.joinpath(".minicc").mkdir(parents=True, exist_ok=True)
    _allowlist_path(workspace).write_text(
        json.dumps({"sessions": {"keep-me": {"commands": ["pytest"], "paths": [], "tools": []}}}),
        encoding="utf-8",
    )


def _read_sessions(workspace: Path) -> dict[str, Any]:
    return json.loads(_allowlist_path(workspace).read_text(encoding="utf-8"))["sessions"]


def _take_one_byte(handle: Any) -> bool:
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
    try:
        handle.seek(0)
        if msvcrt is not None:
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        elif fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


def _hold_sidecar(lock_path: Path) -> Any:
    """Take the sidecar the way a neighbour process would, and keep holding it."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+")  # noqa: SIM115 - the neighbour keeps it open
    if not _take_one_byte(handle):
        handle.close()
        raise AssertionError(f"锁字节没有被本测试占到，邻居占不住: {lock_path.as_posix()}")
    return handle


def _release_sidecar(handle: Any) -> None:
    try:
        _drop_one_byte(handle)
    finally:
        handle.close()


def test_a_neighbour_holding_the_sidecar_refuses_the_replacement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _produce_original(tmp_path)
    before = _read_sessions(tmp_path)

    reads: list[Path] = []
    real_load = al.load_allowlist

    def spy_load(workspace: Path) -> dict[str, Any]:
        reads.append(Path(workspace))
        return real_load(workspace)

    monkeypatch.setattr(al, "load_allowlist", spy_load)

    lock_path = sidecar_path_for(_allowlist_path(tmp_path))
    holder = _hold_sidecar(lock_path)
    try:
        with pytest.raises(al.AllowlistError) as excinfo:
            al.replace_session_rules(tmp_path, "new-session", commands=["git"])
    finally:
        _release_sidecar(holder)

    assert reads == [], "锁没拿到时连读都不许做：单个快照罩住读写两半"
    assert _read_sessions(tmp_path) == before, "拒绝必须意味着文件原样：不降级成无锁写"
    assert "allowlist.json" in str(excinfo.value), "拒绝必须点名文件"


def test_without_a_neighbour_the_replacement_lands(tmp_path: Path) -> None:
    _produce_original(tmp_path)
    out = al.replace_session_rules(tmp_path, "new-session", commands=["git"])
    assert out["commands"] == ["git"]
    sessions = _read_sessions(tmp_path)
    assert sessions["keep-me"]["commands"] == ["pytest"], "已有会话的规则不能丢"
    assert sessions["new-session"]["commands"] == ["git"]


def test_the_refusal_message_states_the_derived_ceiling(tmp_path: Path) -> None:
    _produce_original(tmp_path)
    lock_path = sidecar_path_for(_allowlist_path(tmp_path))
    holder = _hold_sidecar(lock_path)
    try:
        with pytest.raises(al.AllowlistError) as excinfo:
            al.replace_session_rules(tmp_path, "new-session", commands=["git"])
    finally:
        _release_sidecar(holder)
    message = str(excinfo.value)
    assert "上限" in message
    # The ceiling is derived from the outcome the lock reports (attempts x delay);
    # the default budget is 40 attempts at 50ms, and the message must not invent a number.
    assert "40 次" in message and "0.05" in message


def test_the_sidecar_is_named_after_the_allowlist(tmp_path: Path) -> None:
    _produce_original(tmp_path)
    expected = _allowlist_path(tmp_path).with_name(_allowlist_path(tmp_path).name + LOCK_SUFFIX)
    assert sidecar_path_for(_allowlist_path(tmp_path)) == expected


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-W", "error"]))
