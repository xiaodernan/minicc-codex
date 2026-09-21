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

from minicc.session import SessionError, SessionStore

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


def test_single_writer_still_works(tmp_path: Path) -> None:
    store = SessionStore(tmp_path, "solo")
    store.save(_payload_messages("A", 0))
    writer, round_index = _assert_intact(store.path)
    assert (writer, round_index) == ("A", 0)
