"""M3-T7: SessionStore concurrent-write durability.

The old writer used a fixed ``<session>.tmp`` path, so two concurrent ``save()``
calls (web process + detached worker subprocess, or two threads) collided on the
same temp file and raised ``WinError 32`` while leaving the session file missing
or torn. These tests pin the fix: per-call unique temp name + atomic replace +
cross-process lock. Each writer always lands a *complete* payload, so the final
JSON parses and belongs entirely to one writer (never an interleaved blend).
"""

from __future__ import annotations

import json
import multiprocessing
import re
import threading
from pathlib import Path

import pytest

from minicc import session as session_module
from minicc.session import (
    _READ_ATTEMPTS,
    _read_text_with_retry,
    SessionError,
    SessionStore,
)

_WRITER_RE = re.compile(r"^writer-([AB])-round-(\d+)-x+$")


def _payload_messages(writer: str, round_index: int) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": f"writer-{writer}-round-{round_index}-" + "x" * 500},
    ]


def _assert_intact(path: Path) -> tuple[str, int]:
    """Final file must parse and contain exactly one writer's complete payload."""
    assert path.is_file(), "session file vanished under concurrent writes"
    payload = json.loads(path.read_text(encoding="utf-8"))
    messages = payload["messages"]
    assert isinstance(messages, list) and len(messages) == 2
    match = _WRITER_RE.fullmatch(messages[1]["content"])
    assert match is not None, f"torn/interleaved content: {messages[1]['content'][:40]!r}"
    return match.group(1), int(match.group(2))


def test_concurrent_thread_saves_never_corrupt(tmp_path: Path) -> None:
    store = SessionStore(tmp_path, "shared")
    errors: list[BaseException] = []

    def writer(name: str) -> None:
        local = SessionStore(tmp_path, "shared")
        try:
            for round_index in range(20):
                local.save(_payload_messages(name, round_index))
        except BaseException as exc:  # noqa: BLE001 - collected for assertion
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(name,)) for name in ("A", "B")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, f"concurrent save raised: {errors!r}"
    _assert_intact(store.path)
    # No stray temp files left behind.
    leftovers = [p.name for p in store.path.parent.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def _process_writer(workspace: str, writer: str, rounds: int) -> str | None:
    try:
        store = SessionStore(Path(workspace), "shared")
        for round_index in range(rounds):
            store.save(_payload_messages(writer, round_index))
    except BaseException as exc:  # noqa: BLE001 - returned to parent
        return f"{type(exc).__name__}: {exc}"
    return None


def test_concurrent_process_saves_never_corrupt(tmp_path: Path) -> None:
    """process mode: two real subprocesses hammering the same session file."""
    ctx = multiprocessing.get_context("spawn")
    workspace = str(tmp_path)
    with ctx.Pool(2) as pool:
        results = pool.starmap(
            _process_writer, [(workspace, "A", 20), (workspace, "B", 20)]
        )
    failures = [r for r in results if r is not None]
    assert not failures, f"process-mode save failed: {failures!r}"
    _assert_intact(SessionStore(tmp_path, "shared").path)


_ROUNDS = 60


def _process_agent(role: str, workspace: str, writer: str) -> str | None:
    """One subprocess: either a writer or a pure reader of the same session.

    ``save()`` itself reads (message ids and the view), so the writers are
    readers too; the extra pure readers only widen the collision window
    against the atomic replace.
    """
    store = SessionStore(Path(workspace), "shared")
    try:
        if role == "writer":
            for round_index in range(_ROUNDS):
                store.save(_payload_messages(writer, round_index))
        else:
            for _ in range(_ROUNDS):
                store.load("system prompt")
                store.load_view()
    except BaseException as exc:  # noqa: BLE001 - returned to parent
        return f"{type(exc).__name__}: {exc}"
    return None


def test_readers_never_surface_a_transient_sharing_violation(tmp_path: Path) -> None:
    """M3-T7 left one side open: the write path retries, the read path did not.

    Windows hands a reader ``PermissionError`` for the few milliseconds another
    process is replacing the file. The checkpoint on disk is always a complete
    payload, so a retry succeeds - but without one this surfaces to the user as
    "session unreadable", and inside ``save()`` the swallowed variant silently
    re-assigns every message id.
    """
    ctx = multiprocessing.get_context("spawn")
    workspace = str(tmp_path)
    SessionStore(tmp_path, "shared").save(_payload_messages("A", 0))
    jobs = [("writer", workspace, "A"), ("writer", workspace, "B")] + [
        ("reader", workspace, "") for _ in range(4)
    ]
    with ctx.Pool(len(jobs)) as pool:
        results = pool.starmap(_process_agent, jobs)
    failures = [r for r in results if r is not None]
    assert not failures, f"concurrent read/write failed: {failures[:3]!r}"
    _assert_intact(SessionStore(tmp_path, "shared").path)


def test_single_writer_still_works(tmp_path: Path) -> None:
    store = SessionStore(tmp_path, "solo")
    store.save(_payload_messages("A", 0))
    writer, round_index = _assert_intact(store.path)
    assert (writer, round_index) == ("A", 0)


class _FlakyPath:
    """Stand in for a file whose first reads fail the way Windows does."""

    def __init__(self, failures: int, text: str) -> None:
        self.remaining = failures
        self.text = text
        self.reads = 0

    def read_text(self, *, encoding: str) -> str:
        self.reads += 1
        if self.remaining:
            self.remaining -= 1
            raise PermissionError(13, "Permission denied")
        return self.text


def test_transient_read_failures_are_retried_not_raised(monkeypatch) -> None:
    monkeypatch.setattr(session_module, "_READ_RETRY_DELAY", 0.0)
    path = _FlakyPath(3, '{"messages": []}')
    assert _read_text_with_retry(path) == '{"messages": []}'  # type: ignore[arg-type]
    assert path.reads == 4


def test_a_permanently_unreadable_file_still_surfaces(monkeypatch) -> None:
    """Bounded retry, not an infinite wait: the last failure is the caller's."""
    monkeypatch.setattr(session_module, "_READ_RETRY_DELAY", 0.0)
    path = _FlakyPath(_READ_ATTEMPTS, "")
    with pytest.raises(PermissionError):
        _read_text_with_retry(path)  # type: ignore[arg-type]
    assert path.reads == _READ_ATTEMPTS
