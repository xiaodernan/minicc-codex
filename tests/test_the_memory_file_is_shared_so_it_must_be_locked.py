"""M8-T527 — 长期记忆文件是全机器共享的，却按私有文件对待。

``MEMORY.md`` 有两个域：``~/.minicc/MEMORY.md``（**全机器每个工作区共用
同一份**）和 ``<工作区>/.minicc/MEMORY.md``（该工作区每个进程共用同一份）。
而 ``MemoryTools.append()`` 的读-改-写只被一把 ``threading.Lock`` 守着 ——
它跟本进程说话，跟别的进程什么也不说。

**写侧（丢条目）**：实测（plane196 上，两个屏障同步的子进程各追加三条，
六轮）::

    round 0: kept=3 want=6 LOST
    ...
    rounds with all entries: 0/6

每一轮都恰好只剩三条 —— 一个子进程的量。带上跨进程侧车锁之后::

    rounds with all entries: 6/6

**读侧（把拒绝说成"没有"）**：``_read_file`` 原来在 ``OSError`` 时返回
``[]``，也就是"没有记忆"。实测（一个进程追加、一个进程读，六秒）::

    {'total': 519, 'empty': 29, 'ok': 490}
    reads that answered 'no memories' while a writer was active: 29/519

修好之后同样的测量是 2/407 —— 而剩下那 2 次当场核对过，**文件那时真的
还不存在**，那是正确答案不是错答案。

这道门禁钉住的是**形状**，不是某次测量：

* 两个进程并发追加，六条都在（真的起子进程，不是在一个进程里起线程）；
* 锁罩住**读和写两半**，不是只罩一半（锁只罩写，两个进程照样能读到同一份
  旧内容再各自写回去）；
* 拿不到锁时**不**降级为无锁写 —— 丢掉一条"最近打开的文件夹"是装饰性的
  （M8-T265 已定），丢掉一条模型以为自己存下的记忆不是，而且没有任何东西
  会说这件事没了；
* 读侧被拒不答"没有记忆"，但**提示词路径不许因此崩掉** —— 用户手工把记忆
  文件改成坏编码，不该让 agent 起不来。

盲点（如实写明）：

* 侧车锁是**建议锁**：它挡得住守规矩的 minicc 进程，挡不住不守规矩的进程。
* 跨进程腿在本机跑（Windows，``msvcrt``）；POSIX 腿用替身 ``fcntl``，只能
  证明代码问对了标志位，证明不了内核会阻塞。
* 本文件不证明"用户手工编辑记忆文件时不会丢条目" —— 那是另一个形状。
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Any

import pytest

from minicc.tools.memory import MemoryEntry, MemoryTools

try:  # Windows
    import msvcrt
except ImportError:  # pragma: no cover - non-Windows
    msvcrt = None  # type: ignore[assignment]

try:  # POSIX
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

REPO = Path(__file__).resolve().parent.parent
MEMORY_NAME = "MEMORY.md"
#: The naming rule this file asserts rather than imports: the sidecar is named
#: after the file it protects.
LOCK_SUFFIX = ".lock"
#: Tokens the shipped refusal sentence carries, so a reword that drops the
#: diagnosis is a finding and not a silent edit.
REFUSAL_TOKENS = ("占用", "没有写入")

#: Two processes, three entries each.
PROCS = 2
EACH = 3
ROUNDS = 4
CHILD_BUDGET = 120.0
KILL_BUDGET = 30.0

CHILD = textwrap.dedent(
    """
    import sys, time
    from pathlib import Path

    repo, workspace, tag, other, each = sys.argv[1:6]
    sys.path.insert(0, repo)
    from minicc.tools.memory import MemoryTools, MemoryEntry

    store = Path(workspace).parent
    tools = MemoryTools(Path(workspace))


    def wait_for(marker, budget):
        deadline = time.monotonic() + budget
        while not marker.is_file():
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.005)
        return True


    for index in range(int(each)):
        # The handshake: both children announce they are ready for this index
        # and wait for the other one to do the same, so the read-read-
        # write-write interleaving is *forced* rather than hoped for.  A
        # gate that does not force the collision passes on the broken code
        # too, and a gate that passes on the broken code is not a gate.
        Path(store, "%s-%d.ready" % (tag, index)).write_text("ready", encoding="utf-8")
        if not wait_for(Path(store, "%s-%d.ready" % (other, index)), 60.0):
            print("WAIT-FAIL", tag, index)
            raise SystemExit(3)
        entry = MemoryEntry(
            id="mem-%s%04d" % (tag, index),
            content="probe %s %d" % (tag, index),
            created="2026-10-27T00:00:00Z",
            source="probe",
            scope="project",
        )
        tools.append(entry)
        print("APPENDED", tag, index, flush=True)
    print("DONE", tag, flush=True)
    """
)


def _workspace(tmp_path: Path) -> Path:
    target = tmp_path / "ws"
    (target / ".minicc").mkdir(parents=True)
    return target


def _memory_file(workspace: Path) -> Path:
    return workspace / ".minicc" / MEMORY_NAME


def _sidecar_for(path: Path) -> Path:
    return path.with_name(path.name + LOCK_SUFFIX)


def _take_one_byte(handle: Any) -> bool:
    """Try to take one byte of an open sidecar without waiting.

    The probe is deliberately the same primitive and the same mode the shipped
    lock uses, so "free here" and "free for the code" are one question.
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
    try:
        handle.seek(0)
        if msvcrt is not None:
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        elif fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


def _lock_state(lock_path: Path) -> tuple[bool, bool]:
    """Ask the operating system, out of band, whether one byte is free.

    Returns ``(free, existed)``.  Opening the sidecar is how the shipped code
    creates it too, so code that never makes one reads as "free".
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
    """Take the sidecar the way a neighbour process would, and keep holding it."""
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


# --- the two processes, forced into the interleaving -------------------------


def _run_round(root: Path, index: int) -> dict[str, Any]:
    """One forced interleaving, reported as raw readings - no judgement here."""
    store = root / f"store-{index}"
    store.mkdir(parents=True)
    workspace = store / "ws"
    (workspace / ".minicc").mkdir(parents=True)
    script = store / "child.py"
    script.write_text(CHILD, encoding="utf-8")
    procs = []
    for number in range(PROCS):
        other = (number + 1) % PROCS
        procs.append(
            subprocess.Popen(
                [
                    sys.executable,
                    str(script),
                    str(REPO),
                    str(workspace),
                    f"p{number}",
                    f"p{other}",
                    str(EACH),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(store),
                env=dict(os.environ, PYTHONIOENCODING="utf-8"),
            )
        )
    reports: dict[int, tuple[int, str, str]] = {}
    for number, proc in enumerate(procs):
        try:
            stdout, stderr = proc.communicate(timeout=CHILD_BUDGET)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate(timeout=KILL_BUDGET)
            stdout += f"\nTIMEOUT after {CHILD_BUDGET}s"
        reports[number] = (proc.returncode, stdout, stderr)
    path = _memory_file(workspace)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    owners = {
        number: sum(1 for line in text.splitlines() if f"mem-p{number}" in line)
        for number in range(PROCS)
    }
    return {
        "index": index,
        "codes": {number: code for number, (code, _, _) in reports.items()},
        "stderr": {number: err for number, (_, _, err) in reports.items()},
        "entries": sum(owners.values()),
        "owners": owners,
    }


@pytest.fixture(scope="module")
def race_rounds(tmp_path_factory: pytest.TempPathFactory) -> list[dict[str, Any]]:
    """The measurement both process cases read, taken once for the module."""
    root = tmp_path_factory.mktemp("race")
    return [_run_round(root, index) for index in range(ROUNDS)]


def _describe(rounds: list[dict[str, Any]]) -> str:
    return " | ".join(
        f"round{item['index']}: entries={item['owners']} codes={item['codes']}"
        for item in rounds
    )


def test_both_processes_keep_every_entry_they_appended(race_rounds: list[dict[str, Any]]) -> None:
    """The defect in one clause: six entries appended by two processes leave six behind."""
    assert all(code == 0 for item in race_rounds for code in item["codes"].values()), (
        f"a child died, so the counts below would be measuring the harness: {_describe(race_rounds)}\n"
        + "\n".join(item["stderr"][0][-400:] for item in race_rounds)
    )
    due = PROCS * EACH
    lost = [item for item in race_rounds if item["entries"] != due]
    assert not lost, (
        f"{len(lost)} of {len(race_rounds)} rounds kept fewer than {due} of {due} entries; "
        f"{_describe(race_rounds)}"
    )


def test_neither_process_loses_its_own_entries(race_rounds: list[dict[str, Any]]) -> None:
    """The count can add up while one whole side is gone, so each side is read."""
    assert all(code == 0 for item in race_rounds for code in item["codes"].values()), (
        f"a child died before it could be counted: {_describe(race_rounds)}"
    )
    gone = [
        (item["index"], number, count)
        for item in race_rounds
        for number, count in item["owners"].items()
        if count != EACH
    ]
    assert not gone, (
        f"rounds where a side did not keep its own {EACH} entries: {gone}; {_describe(race_rounds)}"
    )


# --- where the lock lives, and what it covers ---------------------------------


def test_the_lock_sidecar_is_named_after_the_memory_file_it_protects(tmp_path: Path) -> None:
    """One write leaves the memory file and a sidecar named after it."""
    workspace = _workspace(tmp_path)
    tools = MemoryTools(workspace)
    tools.append(
        MemoryEntry(
            id="mem-aaaaaaaa",
            content="sidecar naming",
            created="2026-10-27T00:00:00Z",
            source="test",
            scope="project",
        )
    )
    names = sorted(path.name for path in (workspace / ".minicc").iterdir())
    assert names == [MEMORY_NAME, MEMORY_NAME + LOCK_SUFFIX], (
        f"a memory file should leave one sidecar that identifies it, saw {names}"
    )
    assert _sidecar_for(_memory_file(workspace)).is_file(), (
        "the sidecar the code names is not the one it takes"
    )


def test_the_lock_is_held_across_the_read_and_the_write_not_around_one_of_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The transaction is read *then* write; a lock around either half alone keeps the bug.

    Asked by taking a second handle on the sidecar while the file is being
    **read** - the operating system answers, this file does not read the source
    for a token.  The probe is on the read, not on a private helper: a gate
    that spies a helper name breaks into an ``AttributeError`` against the
    pre-fix code, and a crash is not a finding.
    """
    workspace = _workspace(tmp_path)
    tools = MemoryTools(workspace)
    path = _memory_file(workspace)
    lock = _sidecar_for(path)
    readings: dict[str, tuple[bool, bool]] = {}

    real_read_text = Path.read_text

    def spy_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        text = real_read_text(self, *args, **kwargs)
        if self == path:
            readings["during_read"] = _lock_state(lock)
        return text

    monkeypatch.setattr(Path, "read_text", spy_read_text)
    # Seed the file so that the append really performs a read.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# hand-written\n", encoding="utf-8")
    tools.append(
        MemoryEntry(
            id="mem-bbbbbbbb",
            content="lock coverage",
            created="2026-10-27T00:00:00Z",
            source="test",
            scope="project",
        )
    )

    assert "during_read" in readings, f"the memory file was never read: {sorted(readings)}"
    free, existed = readings["during_read"]
    assert not free, (
        "the sidecar was free while the read-modify-write was in progress "
        f"(free=True means this probe took the byte, i.e. nothing was holding it): {readings}"
    )
    assert existed, f"the probe had to create the sidecar itself, so the lock was never armed: {readings}"


def test_the_first_write_to_an_absent_memory_file_still_arms_the_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lock cannot be an afterthought bolted onto an existing file.

    There is no read on the very first write - the file does not exist yet -
    so the probe watches the **swap**: the lock must already be held when the
    file lands, or a first write is exactly the write that could race.
    """
    workspace = _workspace(tmp_path)
    path = _memory_file(workspace)
    assert not path.exists(), "this case is about the very first write"
    tools = MemoryTools(workspace)
    lock = _sidecar_for(path)
    readings: dict[str, tuple[bool, bool]] = {}

    import minicc.tools.memory as memory_module

    real_replace = memory_module.replace_with_retry

    def spy_replace(source: Path, target: Path, **kwargs: Any) -> None:
        readings["during_write"] = _lock_state(lock)
        return real_replace(source, target, **kwargs)

    monkeypatch.setattr(memory_module, "replace_with_retry", spy_replace)
    tools.append(
        MemoryEntry(
            id="mem-cccccccc",
            content="first write",
            created="2026-10-27T00:00:00Z",
            source="test",
            scope="project",
        )
    )

    assert path.is_file(), "the first write never landed, so nothing below was measured"
    assert "during_write" in readings, f"the swap was never reached: {sorted(readings)}"
    free, existed = readings["during_write"]
    assert not free, (
        "on a memory file that did not exist yet, nothing held the sidecar while the "
        f"file landed (sidecar present before the probe: {existed})"
    )
    assert existed, f"the probe had to create the sidecar itself, so the lock was never armed: {readings}"


def test_the_lock_is_put_back_after_the_write_lands(tmp_path: Path) -> None:
    """A lock nobody releases is a second process waiting out the ceiling per entry."""
    workspace = _workspace(tmp_path)
    tools = MemoryTools(workspace)
    for name in ("a", "b"):
        tools.append(
            MemoryEntry(
                id=f"mem-{name * 8}",
                content=f"entry {name}",
                created="2026-10-27T00:00:00Z",
                source="test",
                scope="project",
            )
        )
    free, existed = _lock_state(_sidecar_for(_memory_file(workspace)))
    assert existed, "the sidecar the code took is gone - it was never the one named after the file"
    assert free, "the sidecar is still held after append() returned"


# --- a refusal is a diagnosis, not a silent loss -----------------------------


def _drive_a_refusal(tmp_path: Path) -> dict[str, Any]:
    """Hold the sidecar as a neighbour would, then run one append through it.

    Returns what escaped, the memory file's bytes afterwards and the sidecar
    state.  Raises nothing it does not mean to report.
    """
    workspace = _workspace(tmp_path)
    path = _memory_file(workspace)
    path.write_text("# hand-written\n", encoding="utf-8")
    holder = _hold_sidecar(_sidecar_for(path))
    escaped: list[BaseException] = []
    try:
        tools = MemoryTools(workspace)
        try:
            tools.append(
                MemoryEntry(
                    id="mem-dddddddd",
                    content="refused write",
                    created="2026-10-27T00:00:00Z",
                    source="test",
                    scope="project",
                )
            )
        except BaseException as exc:  # noqa: BLE001 - the exception class is the reading
            escaped.append(exc)
    finally:
        _release_sidecar(holder)
    return {
        "escaped": escaped,
        "text": path.read_text(encoding="utf-8"),
        "path": path,
    }


def test_a_refused_lock_does_not_write_unlocked(tmp_path: Path) -> None:
    """The whole point: the entry is not silently dropped.

    A refusal that degrades to an unlocked write is the defect this batch is
    about, wearing a different hat.
    """
    report = _drive_a_refusal(tmp_path)
    assert "mem-dddddddd" not in report["text"], (
        "the entry was written even though the lock was refused: "
        f"{report['text']!r}"
    )
    assert report["escaped"], "the refusal was swallowed: the caller was told the write happened"


def test_a_refused_lock_says_so_and_names_the_file(tmp_path: Path) -> None:
    """An operator has to be able to tell 'locked out' from 'nothing to remember'."""
    report = _drive_a_refusal(tmp_path)
    assert report["escaped"], "nothing escaped, so there is no refusal sentence to read"
    message = str(report["escaped"][0])
    for token in REFUSAL_TOKENS:
        assert token in message, f"the refusal never said the write was {token}: {message}"
    assert report["path"].name in message, f"the refusal never named the file: {message}"


# --- the read side: a refusal is not "no memories" ----------------------------


def test_a_refused_read_does_not_answer_no_memories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The read side of the same file, same shape: a refusal is not an answer.

    The file plainly holds an entry; the reader is refused; the answer must
    not be "there are no memories".

    The refusal is **injected** rather than raced for: on Windows a second
    handle does not stop a reader, so a gate that tries to make the read fail
    by holding the file open measures nothing and passes on the broken code
    too.  A gate that passes on the broken code is not a gate.
    """
    workspace = _workspace(tmp_path)
    path = _memory_file(workspace)
    path.write_text(
        "- [mem-eeeeeeee] (created=2026-10-27T00:00:00Z, source=test) kept entry\n",
        encoding="utf-8",
    )
    real_read_text = Path.read_text

    def refusing_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        if self == path:
            raise PermissionError(13, "被另一个进程占用", str(self))
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", refusing_read_text)
    escaped: list[BaseException] = []
    entries: list[Any] = []
    try:
        entries = MemoryTools(workspace).load("project")
    except BaseException as exc:  # noqa: BLE001 - the exception class is the reading
        escaped.append(exc)
    assert escaped, (
        "the read was refused and the module answered "
        f"{entries!r} - that is 'there are no memories', which is a wrong answer"
    )
    assert not entries, f"the refusal produced entries anyway: {entries!r}"
    message = str(escaped[0])
    assert path.name in message, f"the refusal never named the file: {message}"


def test_the_prompt_path_survives_an_unreadable_memory_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A memory file the user broke must not stop the agent from starting.

    The tool surface reports the failure; the prompt surface degrades (and
    says so in the log) rather than taking the whole run down.
    """
    from minicc.prompt import build_system_prompt

    workspace = _workspace(tmp_path)
    path = _memory_file(workspace)
    path.write_bytes(b"- [mem-ffffffff] (created=x, source=y) \xff\xfe not utf-8\n")

    prompt = build_system_prompt(workspace)
    assert "你是 minicc" in prompt, "the prompt could not be built at all"
    assert "长期记忆索引" not in prompt, (
        "a broken memory file produced a memory index anyway"
    )


# --- one home for the mechanism ----------------------------------------------


def test_the_cross_process_lock_has_exactly_one_home() -> None:
    """The sidecar lock has one implementation; the call sites keep their policy.

    Derived from the source tree rather than from a list of names, because a
    hand-written list of "the files that should not have their own copy" is a
    list that goes stale - and a stale list cannot be told apart from a
    complete one.

    The judgement is made on the *mechanism*: a module implements the lock if
    it asks the operating system for a byte range itself (``msvcrt.locking``
    or ``fcntl.flock``).  Asking for the byte is the mechanism; everything
    else around it (the budget, what a refusal means) is a policy and stays
    with the call site.
    """
    package = REPO / "minicc"
    homes: dict[str, list[int]] = {}
    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        lines: list[int] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else ""
            if name in {"locking", "flock"}:
                lines.append(node.lineno)
        if lines:
            homes[path.relative_to(REPO).as_posix()] = sorted(lines)
    assert set(homes) == {"minicc/sidecar_lock.py"}, (
        "the cross-process lock is implemented in more than one place, so a fix to one "
        "copy leaves the other answering differently: "
        + "; ".join(f"{name}:{lines}" for name, lines in sorted(homes.items()))
    )


def test_the_memory_module_asks_the_one_home_for_the_lock() -> None:
    """The call site *calls* the one home; importing it is not enough.

    An import that nothing calls is decoration, and the import is exactly what
    a half-done refactor leaves behind.
    """
    source = (REPO / "minicc" / "tools" / "memory.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = False
    called = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "hold_sidecar":
                    imported = True
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else ""
            if name == "hold_sidecar":
                called = True
    assert imported, "the memory module does not import the shared lock at all"
    assert called, "the memory module imports the shared lock but never calls it"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-W", "error"]))
