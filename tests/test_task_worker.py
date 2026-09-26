"""Detached task worker process tests (daemonization step 2)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from minicc.config import ConfigError, load_config
from minicc.task_store import TaskStore


def _service_config(tmp_path: Path, **extra) -> SimpleNamespace:
    base = dict(
        yolo=False,
        max_concurrent_tasks=2,
        sandbox_mode="host",
        sandbox_image="python:3.11-slim",
        base_url="https://example.test/v1",
        api_key="test-key",
        model="test-model",
        timeout=10,
        tool_mode="auto",
        reasoning_effort="high",
        max_turns=4,
        compact_threshold=300_000,
        context_window_tokens=300_000,
        task_executor="process",
    )
    base.update(extra)
    return SimpleNamespace(**base)


def _wait_until(predicate, *, timeout: float = 30.0, message: str = "condition") -> Any:
    """Poll until ``predicate`` returns something truthy, and return *that value*.

    The raise used to write down only what was waited for.  It now also names how
    long the wait lasted, the budget it ran out of, how many times it looked, and
    the last falsy value it saw - the four things that decide whether a red here
    is a hung worker or a slow machine.  M8-T62's measurement says these waits are
    bounded by a real subprocess, so unlike the in-process waits in
    tests/test_permissions_approval.py the constant is not the suspect; the
    message is what was missing.
    """
    begun = time.monotonic()
    polls = 0
    while True:
        polls += 1
        value = predicate()
        if value:
            return value
        elapsed = time.monotonic() - begun
        if elapsed >= timeout:
            raise AssertionError(
                f"gave up on {message} after {elapsed:.2f}s of a {timeout:.2f}s budget "
                f"({polls} polls, last value {value!r})"
            )
        time.sleep(0.05)


def _parked_worker(tmp_path: Path) -> dict[str, Path]:
    """A worker bootstrap whose *model call* never returns until released.

    The provider is patched inside the worker process, so the cancel flag and
    the lease keep working while the request is parked — which is exactly the
    state a real SDK request puts a worker in. ``alive`` is appended to on every
    tick, so a reader can tell whether this process is still executing without
    owning its handle.
    """
    paths = {
        "release": tmp_path / "release-provider",
        "started": tmp_path / "provider-starts",
        "alive": tmp_path / "worker-alive.log",
    }
    script = tmp_path / "parked_worker.py"
    script.write_text(textwrap.dedent(f"""
        import asyncio
        import runpy
        from pathlib import Path
        from minicc.llm.fake import FakeProvider

        RELEASE = Path({str(paths['release'])!r})
        STARTED = Path({str(paths['started'])!r})
        ALIVE = Path({str(paths['alive'])!r})

        original_chat = FakeProvider.chat
        async def controlled_chat(self, messages, tools, on_delta=None):
            if tools is not None:
                with STARTED.open("a", encoding="utf-8") as handle:
                    handle.write("started\\n")
                if on_delta:
                    on_delta("a" * 16050)
                while not RELEASE.exists():
                    with ALIVE.open("a", encoding="utf-8") as handle:
                        handle.write("tick\\n")
                    await asyncio.sleep(0.05)
                if on_delta:
                    on_delta("after-host-restart-")
            return await original_chat(self, messages, tools, on_delta)

        FakeProvider.chat = controlled_chat
        runpy.run_module("minicc.task_worker", run_name="__main__")
    """), encoding="utf-8")
    paths["script"] = script
    return paths


def _spawn_parked_worker(command: list[str], script: Path) -> list[str]:
    """Replace ``python -m minicc.task_worker`` with the parked bootstrap."""
    return [command[0], str(script), *command[3:]]


def _submit_parked_task(service: Any, tmp_path: Path, session_id: str) -> str:
    return service.tasks.submit({
        "message": "Summarize this workspace",
        "session_id": session_id,
        "workspace_path": str(tmp_path),
        "allow_changes": False,
    })["task_id"]


def _inside_parked_model_call(store: TaskStore, task_id: str, alive: Path) -> dict:
    snapshot = _wait_until(
        lambda: (store.get(task_id) or {}) if (store.get(task_id) or {}).get("stream_length", 0) >= 16050 else None,
        timeout=120,
        message=f"worker {task_id} to reach the parked model call",
    )
    _wait_until(lambda: alive.is_file() and alive.stat().st_size > 0, message="parked worker heartbeat")
    return snapshot


def test_config_parses_task_executor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MINICC_API_KEY", "test-key")
    monkeypatch.setenv("MINICC_TASK_EXECUTOR", "process")
    assert load_config().task_executor == "process"
    monkeypatch.setenv("MINICC_TASK_EXECUTOR", "banana")
    with pytest.raises(ConfigError, match="MINICC_TASK_EXECUTOR"):
        load_config()


def test_worker_subprocess_completes_and_persists(tmp_path: Path) -> None:
    store_path = tmp_path / "tasks.sqlite3"
    store = TaskStore(store_path)
    result = subprocess.run(
        [
            sys.executable, "-m", "minicc.task_worker",
            "--workspace", str(tmp_path),
            "--task-id", "task-worker-e2e",
            "--session-id", "worker-test",
            "--message", "worker 子进程任务",
            "--store-path", str(store_path),
            "--config-json", json.dumps({
                "yolo": False, "max_concurrent_tasks": 2, "sandbox_mode": "host",
                "sandbox_image": "python:3.11-slim", "base_url": "https://example.test/v1",
                "api_key": "k", "model": "m", "timeout": 10, "tool_mode": "auto",
                "reasoning_effort": "high", "max_turns": 4, "compact_threshold": 300000,
                "context_window_tokens": 300000,
            }),
            "--fake-provider",
        ],
        capture_output=True, text=True, errors="replace", timeout=180,
    )
    assert result.returncode == 0, result.stderr[-800:]
    snapshot = store.get("task-worker-e2e")
    assert snapshot is not None
    assert snapshot["status"] == "completed"
    assert "fake-provider-answer" in str((snapshot.get("result") or {}).get("answer"))
    assert snapshot["heartbeat_at_epoch"] > 0


def test_worker_cancellation_via_flag_file(tmp_path: Path) -> None:
    """A cancellation flag file written before start yields a cancelled record."""
    store_path = tmp_path / "tasks.sqlite3"
    store = TaskStore(store_path)
    cancel_file = tmp_path / ".minicc" / "cancel" / "task-c.flag"
    cancel_file.parent.mkdir(parents=True, exist_ok=True)
    cancel_file.write_text("cancelled", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable, "-m", "minicc.task_worker",
            "--workspace", str(tmp_path),
            "--task-id", "task-c",
            "--message", "会被取消的任务",
            "--store-path", str(store_path),
            "--cancel-file", str(cancel_file),
            "--config-json", json.dumps({
                "yolo": False, "max_concurrent_tasks": 2, "sandbox_mode": "host",
                "sandbox_image": "x", "base_url": "https://example.test/v1",
                "api_key": "k", "model": "m", "timeout": 10, "tool_mode": "auto",
                "reasoning_effort": "high", "max_turns": 4, "compact_threshold": 300000,
                "context_window_tokens": 300000,
            }),
            "--fake-provider",
        ],
        capture_output=True, text=True, errors="replace", timeout=180,
    )
    assert result.returncode == 0, result.stderr[-800:]
    snapshot = store.get("task-c")
    assert snapshot is not None
    assert snapshot["status"] == "cancelled"


def test_manager_process_mode_runs_task_in_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Full loop: web submit -> worker subprocess -> store -> manager mirror."""
    from minicc.web import AgentService

    monkeypatch.setenv("MINICC_FAKE_PROVIDER", "1")
    store_path = tmp_path / "tasks.sqlite3"
    service = AgentService(tmp_path, _service_config(tmp_path), task_store=TaskStore(store_path))
    try:
        submitted = service.tasks.submit({
            "message": "进程模式端到端",
            "session_id": "proc-test",
            "workspace_path": str(tmp_path),
            "allow_changes": False,
        })
        task_id = submitted["task_id"]
        deadline = time.time() + 120
        snapshot = None
        while time.time() < deadline:
            snapshot = service.tasks.get(task_id)
            if snapshot["status"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(1.0)
        assert snapshot is not None
        assert snapshot["status"] == "completed", snapshot.get("error")
        assert "fake-provider-answer" in str(snapshot.get("answer") or snapshot.get("stream_text") or "")
        # The durable store holds the worker's own terminal snapshot too.
        stored = TaskStore(store_path).get(task_id)
        assert stored is not None and stored["status"] == "completed"
        # M3-T6: the api_key travels over stdin, so no plaintext config file is
        # ever written to the worker dir (and the request file is cleaned up).
        worker_dir = tmp_path / ".minicc" / "worker"
        assert not list(worker_dir.glob("*.config.json"))
        assert not list(worker_dir.glob("*.request.json"))
    finally:
        service.shutdown()


def test_clean_shutdown_aborts_a_worker_that_ignores_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M8-T14 (option A): shutting down must stop the work it launched.

    The worker is parked inside a model request, so it cannot observe its cancel
    flag and the cooperative path cannot finish — escalation to ``terminate()``
    is the only way out. Three observable consequences are pinned here:

    * the process really stops appending to its liveness log,
    * the durable record reads ``cancelled`` (a record left ``running`` would be
      adopted by auto-resume on the next start, i.e. shutdown would restart the
      work the user just stopped),
    * a replacement host does not pick the task up at all.
    """
    from minicc.task_manager import TaskManager
    from minicc.web import AgentService

    monkeypatch.setenv("MINICC_FAKE_PROVIDER", "1")
    parked = _parked_worker(tmp_path)
    original_command = TaskManager._worker_command
    monkeypatch.setattr(
        TaskManager, "_worker_command",
        lambda self, *args, **kwargs: _spawn_parked_worker(
            original_command(self, *args, **kwargs), parked["script"]
        ),
    )
    store = TaskStore(tmp_path / "tasks.sqlite3")
    service = AgentService(tmp_path, _service_config(tmp_path), task_store=store)
    task_id = ""
    try:
        task_id = _submit_parked_task(service, tmp_path, "abort-session")
        snapshot = _inside_parked_model_call(store, task_id, parked["alive"])
        assert snapshot["status"] == "running"

        started = time.monotonic()
        service.shutdown()
        # Bounded: cooperative grace + terminate wait, not the worker's lifetime.
        assert time.monotonic() - started < 40, "shutdown waited on the worker forever"

        ticks = parked["alive"].stat().st_size
        time.sleep(1.0)
        assert parked["alive"].stat().st_size == ticks, "worker kept running after shutdown"

        final = store.get(task_id) or {}
        assert final.get("status") == "cancelled", final
        assert store.get_lease(task_id) is None
        assert not (tmp_path / ".minicc" / "cancel" / f"{task_id}.flag").exists()

        replacement = AgentService(
            tmp_path, _service_config(tmp_path, auto_resume_on_start=True), task_store=store
        )
        try:
            # History is loaded on startup either way; what must NOT happen is
            # adopting it as live work or re-queuing it.
            assert replacement.tasks.get(task_id)["status"] == "cancelled"
            assert task_id not in replacement.tasks._detached_tasks
        finally:
            replacement.shutdown()
        parked["release"].touch()
    finally:
        parked["release"].touch()
        service.shutdown()


def test_worker_survives_host_crash_and_continues_long_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A host that dies *without* shutting down must not take its worker down.

    This is the other half of the M8-T14 decision: option A aborts workers on a
    clean ``shutdown()``, and that must not cost the crash-recovery contract, so
    the host here is a real child process that is killed outright. It cannot run
    any cleanup, which is the only faithful way to produce a crash — patching
    ``shutdown()`` out in-process would only simulate the absence of cleanup.
    """
    monkeypatch.setenv("MINICC_FAKE_PROVIDER", "1")
    parked = _parked_worker(tmp_path)
    store_path = tmp_path / "tasks.sqlite3"
    task_id_file = tmp_path / "task-id.txt"
    host_script = tmp_path / "crashing_host.py"
    host_script.write_text(textwrap.dedent(f"""
        import json, sys, time
        from pathlib import Path
        from types import SimpleNamespace

        from minicc.task_manager import TaskManager
        from minicc.task_store import TaskStore
        from minicc.web import AgentService

        spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        config = SimpleNamespace(**spec["config"])
        script = spec["bootstrap"]
        original_command = TaskManager._worker_command

        def controlled_command(self, *args, **kwargs):
            command = original_command(self, *args, **kwargs)
            return [command[0], script, *command[3:]]

        TaskManager._worker_command = controlled_command
        service = AgentService(
            Path(spec["workspace"]), config, task_store=TaskStore(Path(spec["store_path"]))
        )
        task_id = service.tasks.submit({{
            "message": "Summarize this workspace", "session_id": "crash-session",
            "workspace_path": spec["workspace"], "allow_changes": False,
        }})["task_id"]
        Path(spec["task_id_file"]).write_text(task_id, encoding="utf-8")
        while True:
            time.sleep(0.2)
    """), encoding="utf-8")
    spec = tmp_path / "host-spec.json"
    spec.write_text(json.dumps({
        "workspace": str(tmp_path),
        "store_path": str(store_path),
        "task_id_file": str(task_id_file),
        "bootstrap": str(parked["script"]),
        "config": {**vars(_service_config(tmp_path)), "auto_resume_on_start": True},
    }), encoding="utf-8")
    source_root = str(Path(__file__).resolve().parent.parent)
    env = os.environ.copy()
    env["PYTHONPATH"] = source_root + os.pathsep + env.get("PYTHONPATH", "")
    # Logging from the host goes to a file, not a pipe: nobody reads a pipe while
    # the test drives the worker, and a full pipe would block the very process
    # whose crash we are simulating.
    host_log = (tmp_path / "host.log").open("ab")
    host = subprocess.Popen(
        [sys.executable, str(host_script), str(spec)],
        cwd=str(tmp_path), env=env, stdout=host_log, stderr=host_log,
    )
    replacement = None
    try:
        task_id = _wait_until(
            lambda: task_id_file.read_text(encoding="utf-8") if task_id_file.is_file() else None,
            timeout=90, message="crash host to submit its task",
        )
        store = TaskStore(store_path)
        original = _inside_parked_model_call(store, task_id, parked["alive"])
        original_owner = store.get_lease(task_id)["owner"]

        # Kill the host outright: no atexit, no shutdown, no cancel flag.
        host.kill()
        assert host.wait(timeout=30) != 0
        assert (store.get(task_id) or {}).get("status") == "running"
        assert not (tmp_path / ".minicc" / "cancel" / f"{task_id}.flag").exists()
        ticks = parked["alive"].stat().st_size
        time.sleep(1.0)
        assert parked["alive"].stat().st_size > ticks, "worker died with its host"

        from minicc.web import AgentService

        replacement = AgentService(
            tmp_path, _service_config(tmp_path, auto_resume_on_start=True), task_store=store
        )
        assert list(replacement.tasks.tasks) == [task_id]
        assert replacement.tasks.get(task_id)["status"] == "running"
        assert store.get_lease(task_id)["owner"] == original_owner
        assert store.get(task_id)["worker_pid"] == original["worker_pid"]

        parked["release"].touch()
        _wait_until(
            lambda: replacement.tasks.get(task_id)["status"] in {"completed", "failed", "cancelled"},
            timeout=120, message="survived worker to finish",
        )
        final = replacement.tasks.get(task_id)
        assert final["status"] == "completed", final.get("error")
        assert final["stream_length"] > 16050
        assert "after-host-restart-fake-provider-answer" in final["stream_text"]
        # M4-T1: the fake provider emits one readonly tool call before its final
        # answer, so a completing task makes exactly two agent-stage model
        # calls. Asserting the precise count still proves the survived worker was
        # never re-spawned (a restart would duplicate the whole sequence).
        assert parked["started"].read_text(encoding="utf-8").splitlines() == ["started", "started"]
        assert store.get(task_id)["status"] == "completed"
    finally:
        parked["release"].touch()
        if host.poll() is None:
            host.kill()
        try:
            host.wait(timeout=30)
        except subprocess.TimeoutExpired:
            pass
        host_log.close()
        if replacement is not None:
            replacement.shutdown()


def test_shutdown_reaps_detached_worker_without_resource_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M4-7 / M8-T14: a worker must never be dropped while its handle is live.

    ``pytest -W error`` used to fail with "ResourceWarning: subprocess N is
    still running" because ``_monitor_worker`` raised ``WorkerDetached`` during
    shutdown and the Popen handle was dropped unreferenced. Handles are now
    reaped or handed to a background reaper on every exit path, so no warning is
    emitted and the registry drains.
    """
    import gc
    import warnings

    from minicc.web import AgentService

    monkeypatch.setenv("MINICC_FAKE_PROVIDER", "1")
    store_path = tmp_path / "tasks.sqlite3"
    store = TaskStore(store_path)
    service = AgentService(tmp_path, _service_config(tmp_path), task_store=store)
    try:
        task_id = service.tasks.submit({
            "message": "reap me",
            "session_id": "reap-session",
            "workspace_path": str(tmp_path),
            "allow_changes": False,
        })["task_id"]
        deadline = time.time() + 120
        while time.time() < deadline and (store.get(task_id) or {}).get("status") not in {
            "completed", "failed", "cancelled",
        }:
            time.sleep(0.2)
        assert (store.get(task_id) or {}).get("status") == "completed"

        manager = service.tasks
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            service.shutdown()
            gc.collect()
        leaked = [str(item.message) for item in caught if "still running" in str(item.message)]
        assert leaked == [], leaked
        # Every handle is either reaped or owned by a reaper thread: nothing is
        # left registered for this manager.
        assert manager._worker_processes == {}
    finally:
        service.shutdown()


def test_release_path_leaves_a_running_worker_alive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Only a shutdown aborts; retiring a handle off the normal path must not.

    A monitor that returns while its worker is still running (lost lease, an
    expired snapshot read) hands the handle to the reaper and leaves execution
    to the lease in SQLite — the crash-recovery contract above depends on that
    distinction, so the same registry entry point is checked in both modes.
    """
    from minicc.web import AgentService

    monkeypatch.setenv("MINICC_FAKE_PROVIDER", "1")
    service = AgentService(
        tmp_path, _service_config(tmp_path), task_store=TaskStore(tmp_path / "tasks.sqlite3")
    )
    manager = service.tasks
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        manager._register_worker_process("task-alive", child)
        manager._retire_worker_process("task-alive")
        assert manager._worker_processes == {}
        assert child.poll() is None, "normal retirement must not kill the worker"
    finally:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)
        service.shutdown()


def test_shutdown_abort_path_terminates_a_worker_it_cannot_cancel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The unit form of option A, without a task record to cancel through.

    An unresolvable workspace means no cancel flag, so escalation to
    ``terminate()`` must be what stops the child — and the handle must still be
    reaped rather than dropped.
    """
    from minicc.web import AgentService

    monkeypatch.setenv("MINICC_FAKE_PROVIDER", "1")
    service = AgentService(
        tmp_path, _service_config(tmp_path), task_store=TaskStore(tmp_path / "tasks.sqlite3")
    )
    manager = service.tasks
    manager._closing = True
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        manager._register_worker_process("task-dead", child)
        started = time.monotonic()
        manager._retire_worker_process("task-dead")
        assert child.poll() is not None, "shutdown left the worker running"
        # No cancel flag was possible, so the wait must be the terminate bound.
        assert time.monotonic() - started < 15
        assert manager._worker_processes == {}
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
        service.shutdown()


def test_the_worker_wait_writes_down_its_own_patience() -> None:
    """M8-T62: ``timed out waiting for X`` was the whole message, and it was thin.

    These gates wait on a real worker subprocess, so their 30-120s budgets are not
    the suspect that the in-process 2.0s budgets in
    tests/test_permissions_approval.py turned out to be.  What was missing is the
    reading that decides whether a red here is a hung worker or a slow machine:
    how long it waited, what it allowed itself, how many times it looked, and the
    last falsy value it saw.  This forces the miss with no subprocess involved, so
    the failure branch is the only thing under test.
    """
    begun = time.monotonic()
    with pytest.raises(AssertionError) as caught:
        _wait_until(lambda: None, timeout=0.2, message="a value that never arrives")
    message = str(caught.value)
    assert "gave up on a value that never arrives" in message, message
    assert "of a 0.20s budget" in message, message
    assert "last value None" in message, message
    polls = int(message.split("(")[1].split(" polls")[0])
    assert polls >= 2, f"the wait never polled: {message}"
    elapsed = time.monotonic() - begun
    assert 0.2 <= elapsed < 5.0, (
        f"the message claims a 0.20s budget but the wait lasted {elapsed:.2f}s"
    )
