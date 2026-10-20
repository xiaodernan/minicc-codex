"""M8-T292 — 一次扫描抓到的五条：memo 键、共享文件的读-改-写、整读与"拒绝路径"

这一批做完之后做了一次扫描，报出五条问题：

| 编号 | 位置 | 问题 |
| --- | --- | --- |
| M8-T292a | `agent/retrieval.py` | 索引的 per-file memo 键只有 `(mtime, size)` → **等长原地改写**（本仓库自己量过：约 32% 的快速写）会让索引**永久**陈旧，命中的是文件里已经**不存在**的文本 |
| M8-T292b | `static_assets.py` | 资源缓存键同样缺 `ctime`/`ino` → 返回**旧字节 + 旧 ETag**，而 URL 是内容寻址且 `immutable`，浏览器一年不会再问 |
| M8-T292c | `snapshots.py` | manifest 的读-改-写只有**实例级**锁，而 Web 每个请求建一个 journal、服务器是线程的 → 并发下**静默丢条目**，restore 报"跳过" |
| M8-T292d | `output_style.py` | 风格文件**无上限整读**（上限只作用在切片上），且读失败被吞成 `""` → 用户的行文偏好凭空消失且无任何诊断 |
| M8-T292e | `webserver.py` | POST 的**第三条**拒绝路径（长度非法/缺长度）既不 drain 也不关连接 → keep-alive 连接上的下一个请求被残留字节错位 |

This door pins all five.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from minicc.agent.retrieval import LocalEvidenceIndex
from minicc.output_style import load_output_style
from minicc.snapshots import SnapshotJournal


# --- M8-T292a: the index memo must notice an equal-length rewrite ---------


def test_the_index_notices_an_equal_length_rewrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rewrite that does not advance ``st_mtime_ns`` used to be invisible.

    The index's own contract is that a refresh of an unchanged tree opens
    **no** file body (``tests/test_retrieval_enhanced.py``), so the change
    cannot be detected by reading the content on every tick.  What the fix
    does is bound the window: a record older than the age bound is rebuilt
    on the next refresh, so the staleness is bounded instead of permanent.

    The bound is what the test moves, so the property is checked without
    waiting a minute.
    """
    import minicc.agent.retrieval as retrieval_module

    monkeypatch.setattr(retrieval_module, "RECORD_MAX_AGE_SECONDS", 0.0)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "a.py"
    target.write_text("alpha", encoding="utf-8")

    index = LocalEvidenceIndex(workspace, refresh_interval=3600.0)
    index.refresh()
    assert index.search("alpha"), "the original text was not indexed"

    stat = target.stat()
    target.write_text("bravo", encoding="utf-8")
    # Keep the mtime exactly where it was.
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))

    index.refresh()
    assert index.search("bravo"), "the new text was not indexed"
    assert not index.search("alpha"), (
        "the index still reports text the file no longer contains"
    )


def test_an_unchanged_refresh_still_opens_no_file_body(tmp_path: Path) -> None:
    """The control: the age bound does not turn every tick into a re-read.

    This is the index's own contract, and the fix must not have weakened
    it: a refresh right after a build reuses the records, so no body is
    read - only the walk and the stats happen.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()
    for index in range(5):
        (workspace / f"f{index}.py").write_text(f"x = {index}\n", encoding="utf-8")

    index = LocalEvidenceIndex(workspace, refresh_interval=3600.0)
    index.refresh()
    index.refresh()
    assert index.stats()["files_rebuilt"] == 0, (
        "the records were rebuilt although nothing changed"
    )


# --- M8-T292b: the asset cache must notice the same rewrite ---------------


def test_the_asset_cache_does_not_serve_the_old_bytes(tmp_path: Path) -> None:
    """The ETag is computed from the cached bytes, so a stale key means a
    stale ETag - and the URL is content-addressed and immutable."""
    from minicc.static_assets import asset_response

    root = tmp_path / "web"
    (root / "assets").mkdir(parents=True)
    name = "assets/app.0123456789abcdef.js"
    target = root / name
    target.write_text("A" * 2000, encoding="utf-8")

    first, _headers = asset_response(root, name)
    stat = target.stat()
    target.write_text("B" * 2000, encoding="utf-8")
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))

    second, headers = asset_response(root, name)
    assert first != second, "the cache served the old bytes"
    assert headers.get("ETag") not in (None, "")


# --- M8-T292c: two journals must not lose each other's entries -----------


def test_two_journals_for_one_task_do_not_lose_entries(tmp_path: Path) -> None:
    """The manifest is shared; the lock has to span instances.

    The two journals are used **concurrently**: each holds its own
    instance lock, so without a lock that spans instances both read the
    same manifest and one save overwrites the other's entry.  The write
    is slowed down so the interleaving is deterministic rather than a
    race that happens to go one way.
    """
    import minicc.snapshots as snapshots_module
    from minicc.snapshots import capture
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "a.py").write_text("a\n", encoding="utf-8")
    (workspace / "b.py").write_text("b\n", encoding="utf-8")
    capture(workspace, "t1")

    real_save = snapshots_module._save
    real_load = snapshots_module._load

    inside_save = threading.Event()
    release_save = threading.Event()
    second_load = threading.Event()
    loads = {"count": 0}

    def counting_load(dest: Path, root: Path) -> dict[str, Any]:
        loads["count"] += 1
        if loads["count"] >= 2:
            second_load.set()
        return real_load(dest, root)

    def slow_save(dest: Path, manifest: dict[str, Any]) -> None:
        # Hold the write open, so the second writer (if it is not blocked by
        # a lock that spans instances) reads the manifest **before** this
        # one lands - which is the interleaving that loses an entry.
        inside_save.set()
        release_save.wait(timeout=30)
        real_save(dest, manifest)

    snapshots_module._save = slow_save  # type: ignore[assignment]
    snapshots_module._load = counting_load  # type: ignore[assignment]
    try:
        first = SnapshotJournal(workspace, "t1")
        second = SnapshotJournal(workspace, "t1")

        errors: list[BaseException] = []

        def write(journal: SnapshotJournal, name: str) -> None:
            try:
                journal.before_write(workspace / name)
            except BaseException as exc:  # noqa: BLE001 - reported below
                errors.append(exc)

        first_thread = threading.Thread(target=write, args=(first, "a.py"))
        second_thread = threading.Thread(target=write, args=(second, "b.py"))
        first_thread.start()
        assert inside_save.wait(timeout=30), "the first journal never reached the save"
        second_thread.start()
        # With a lock that spans instances the second writer is blocked
        # before it reads anything, so this never fires - and the wait ends
        # on its timeout.  Without one it fires, and that is the race.
        second_load.wait(timeout=2.0)
        release_save.set()
        for thread in (first_thread, second_thread):
            thread.join(timeout=30)
            assert not thread.is_alive(), "a journal thread outlived its join"
        assert not errors, f"a journal raised: {errors}"
    finally:
        snapshots_module._save = real_save  # type: ignore[assignment]
        snapshots_module._load = real_load  # type: ignore[assignment]

    manifest = json.loads(
        (workspace / ".minicc" / "snapshots" / "t1" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert "a.py" in manifest.get("files", []), (
        f"the first journal's entry was lost: {manifest.get('files')}"
    )
    assert "b.py" in manifest.get("files", []), (
        f"the second journal's entry was lost: {manifest.get('files')}"
    )


def test_two_journals_do_not_lose_each_other_s_confirmed_digests(
    tmp_path: Path,
) -> None:
    """The other half of the same read-modify-write needs the same lock.

    ``after_write`` records the **confirmed digest** of a file the task
    wrote.  Losing that entry is worse than losing the pre-image one: the
    file stays ``{"pending": True}`` forever, so ``restore`` finds a
    digest mismatch, records a conflict and **refuses** to put the user's
    file back.
    """
    import minicc.snapshots as snapshots_module
    from minicc.snapshots import capture

    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "a.py").write_text("a\n", encoding="utf-8")
    (workspace / "b.py").write_text("b\n", encoding="utf-8")
    capture(workspace, "t2")

    real_save = snapshots_module._save
    real_load = snapshots_module._load

    inside_save = threading.Event()
    release_save = threading.Event()
    second_load = threading.Event()
    loads = {"count": 0}

    def counting_load(dest: Path, root: Path) -> dict[str, Any]:
        loads["count"] += 1
        if loads["count"] >= 2:
            second_load.set()
        return real_load(dest, root)

    def slow_save(dest: Path, manifest: dict[str, Any]) -> None:
        inside_save.set()
        release_save.wait(timeout=30)
        real_save(dest, manifest)

    snapshots_module._save = slow_save  # type: ignore[assignment]
    snapshots_module._load = counting_load  # type: ignore[assignment]
    try:
        first = SnapshotJournal(workspace, "t2")
        second = SnapshotJournal(workspace, "t2")

        errors: list[BaseException] = []

        def confirm(journal: SnapshotJournal, name: str) -> None:
            try:
                journal.after_write(workspace / name)
            except BaseException as exc:  # noqa: BLE001 - reported below
                errors.append(exc)

        first_thread = threading.Thread(target=confirm, args=(first, "a.py"))
        second_thread = threading.Thread(target=confirm, args=(second, "b.py"))
        first_thread.start()
        assert inside_save.wait(timeout=30), "the first journal never reached the save"
        second_thread.start()
        second_load.wait(timeout=2.0)
        release_save.set()
        for thread in (first_thread, second_thread):
            thread.join(timeout=30)
            assert not thread.is_alive(), "a journal thread outlived its join"
        assert not errors, f"a journal raised: {errors}"
    finally:
        snapshots_module._save = real_save  # type: ignore[assignment]
        snapshots_module._load = real_load  # type: ignore[assignment]

    manifest = json.loads(
        (workspace / ".minicc" / "snapshots" / "t2" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    touched = manifest.get("touched", {})
    assert "a.py" in touched, f"the first digest was lost: {touched}"
    assert "b.py" in touched, f"the second digest was lost: {touched}"
    assert touched.get("a.py", {}).get("digest"), "the entry has no confirmed digest"


# --- M8-T292d: the style file is read bounded, and a failure is reported --


def test_the_style_file_is_read_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The ceiling must bound the read, not only the slice."""
    workspace = tmp_path / "ws"
    (workspace / ".minicc").mkdir(parents=True)
    (workspace / ".minicc" / "output-style.md").write_text(
        "x" * 5_000_000, encoding="utf-8"
    )

    read_sizes: list[int] = []
    real_open = Path.open

    class _Counting:
        def __init__(self, handle: Any) -> None:
            self._handle = handle

        def read(self, size: int = -1) -> str:
            data = self._handle.read(size)
            read_sizes.append(len(data))
            return data

        def __enter__(self) -> "_Counting":
            self._handle.__enter__()
            return self

        def __exit__(self, *args: object) -> None:
            self._handle.__exit__(*args)

    def counting_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        return _Counting(real_open(self, *args, **kwargs))

    monkeypatch.setattr(Path, "open", counting_open)
    style = load_output_style(workspace, "")
    assert style, "the style was not read at all"
    assert read_sizes and max(read_sizes) <= 4096, (
        f"the file was read in chunks of {max(read_sizes)} characters"
    )


def test_an_unreadable_style_file_is_reported(tmp_path: Path, caplog: Any) -> None:
    """It used to be swallowed into "no style", so the prompt looked normal."""
    import logging

    workspace = tmp_path / "ws"
    (workspace / ".minicc").mkdir(parents=True)
    (workspace / ".minicc" / "output-style.md").write_bytes(b"\xff\xfe reply in Japanese")

    with caplog.at_level(logging.WARNING, logger="minicc.output_style"):
        assert load_output_style(workspace, "") == ""
    assert any("输出风格" in record.message for record in caplog.records), (
        f"the failure was not reported: {[r.message for r in caplog.records]}"
    )


# --- M8-T292e: a rejected POST must not leave the connection mis-framed --


def _read_response(sock: socket.socket) -> tuple[str, bytes] | None:
    """Read one HTTP response: the status line, then the body by length.

    ``None`` means the peer closed the connection.
    """
    data = b""
    while b"\r\n\r\n" not in data:
        try:
            chunk = sock.recv(4096)
        except OSError:
            return None
        if not chunk:
            return None
        data += chunk
    head, _, rest = data.partition(b"\r\n\r\n")
    status = head.split(b"\r\n", 1)[0].decode("latin-1", "replace")
    length = 0
    for line in head.split(b"\r\n")[1:]:
        name, _, value = line.partition(b":")
        if name.strip().lower() == b"content-length":
            length = int(value.strip() or b"0")
    while len(rest) < length:
        try:
            chunk = sock.recv(4096)
        except OSError:
            break
        if not chunk:
            break
        rest += chunk
    return status, rest


def test_a_malformed_content_length_does_not_mis_frame_the_next_request(
    tmp_path: Path,
) -> None:
    """The third rejection path left the body in the socket."""
    from minicc.web import MiniccHTTPServer

    class _Service:
        config = type("C", (), {"max_concurrent_tasks": 1})()
        workspace_info = staticmethod(lambda: {"name": "s", "path": str(tmp_path)})

    server = MiniccHTTPServer(("127.0.0.1", 0), _Service(), auth=None)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
    thread.daemon = True
    thread.start()
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
            # A body **is** sent, so there are bytes left in the socket
            # when the length cannot be parsed.
            sock.sendall(
                b"POST /api/chat HTTP/1.1\r\nHost: x\r\nContent-Length: abc\r\n\r\n"
                + b'{"message": "leftover"}'
            )
            sock.settimeout(5)
            first = _read_response(sock)
            assert first is not None, "the server closed without answering"
            status, _body = first
            assert "400" in status, f"the malformed length was not refused: {status}"

            # The connection must not be reused with the body still in it.
            sock.sendall(b"GET /api/health HTTP/1.1\r\nHost: x\r\n\r\n")
            second = _read_response(sock)
            if second is not None:
                # A live connection has to answer the next request normally.
                # A 400 here would mean the leftover body was parsed as a
                # request - the mis-framing this door is about.
                assert "200" in second[0], (
                    f"the connection was mis-framed by the leftover body: {second[0]}"
                )
    finally:
        server.shutdown()
        server.server_close()
