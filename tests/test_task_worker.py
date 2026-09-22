"""Detached task worker process tests (daemonization step 2)."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace

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
        capture_output=True, text=True, timeout=180,
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
        capture_output=True, text=True, timeout=180,
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


def test_worker_survives_host_restart_and_continues_long_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Restart the actual host while its actual worker is inside a model call."""
    from minicc.task_manager import TaskManager
    from minicc.web import AgentService

    monkeypatch.setenv("MINICC_FAKE_PROVIDER", "1")
    release_file = tmp_path / "release-provider"
    started_file = tmp_path / "provider-starts"
    bootstrap = tmp_path / "controlled_worker.py"
    bootstrap.write_text(textwrap.dedent(f"""
        import asyncio
        import runpy
        from pathlib import Path
        from minicc.llm.fake import FakeProvider

        original_chat = FakeProvider.chat
        async def controlled_chat(self, messages, tools, on_delta=None):
            if tools is not None:
                with Path({str(started_file)!r}).open("a", encoding="utf-8") as handle:
                    handle.write("started\\n")
                if on_delta:
                    on_delta("a" * 16050)
                while not Path({str(release_file)!r}).exists():
                    await asyncio.sleep(0.05)
                if on_delta:
                    on_delta("after-host-restart-")
            return await original_chat(self, messages, tools, on_delta)

        FakeProvider.chat = controlled_chat
        runpy.run_module("minicc.task_worker", run_name="__main__")
    """), encoding="utf-8")
    original_command = TaskManager._worker_command

    def controlled_command(self, *args, **kwargs):
        command = original_command(self, *args, **kwargs)
        return [command[0], str(bootstrap), *command[3:]]

    monkeypatch.setattr(TaskManager, "_worker_command", controlled_command)
    store = TaskStore(tmp_path / "tasks.sqlite3")
    config = _service_config(tmp_path, auto_resume_on_start=True)
    first = AgentService(tmp_path, config, task_store=store)
    replacement = None
    task_id = ""

    def wait_until(predicate, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(0.05)
        raise AssertionError("worker state did not reach the expected checkpoint")

    try:
        task_id = first.tasks.submit({
            "message": "Summarize this workspace", "session_id": "restart-session",
            "workspace_path": str(tmp_path), "allow_changes": False,
        })["task_id"]
        wait_until(lambda: (store.get(task_id) or {}).get("stream_length", 0) >= 16050)
        original = store.get(task_id)
        original_owner = store.get_lease(task_id)["owner"]
        first.shutdown()
        assert store.get(task_id)["status"] == "running"
        assert not (tmp_path / ".minicc" / "cancel" / f"{task_id}.flag").exists()

        replacement = AgentService(tmp_path, config, task_store=store)
        assert list(replacement.tasks.tasks) == [task_id]
        assert replacement.tasks.get(task_id)["status"] == "running"
        assert store.get_lease(task_id)["owner"] == original_owner
        assert store.get(task_id)["worker_pid"] == original["worker_pid"]

        release_file.touch()
        wait_until(lambda: replacement.tasks.get(task_id)["status"] in {"completed", "failed", "cancelled"})
        final = replacement.tasks.get(task_id)
        assert final["status"] == "completed", final.get("error")
        assert final["stream_length"] > 16050
        assert "after-host-restart-fake-provider-answer" in final["stream_text"]
        # M4-T1: the fake provider now emits one readonly tool call before its
        # final answer, so a completing task makes exactly two agent-stage model
        # calls. Asserting the precise count still proves the survived worker
        # was never re-spawned (a restart would duplicate the whole sequence).
        assert started_file.read_text(encoding="utf-8").splitlines() == ["started", "started"]
        assert store.get(task_id)["status"] == "completed"
    finally:
        release_file.touch()
        first.shutdown()
        if replacement is not None:
            replacement.shutdown()


def test_shutdown_reaps_detached_worker_without_resource_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M4-7 / M8-T14: a worker that outlives its host must not leak its handle.

    ``pytest -W error`` used to fail with "ResourceWarning: subprocess N is
    still running" because ``_monitor_worker`` raised ``WorkerDetached`` during
    shutdown and the Popen handle was dropped unreferenced. Option B of the
    audit is pinned here: the worker is deliberately *not* killed (the lease in
    SQLite is the real supervisor), but its handle is reaped or handed to a
    background reaper, so no warning is emitted and the registry drains.
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


def test_detached_worker_handle_is_released_without_killing_the_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The release path must not terminate the child (the restart test depends on it)."""
    import subprocess
    import sys

    from minicc.web import AgentService

    monkeypatch.setenv("MINICC_FAKE_PROVIDER", "1")
    service = AgentService(
        tmp_path, _service_config(tmp_path), task_store=TaskStore(tmp_path / "tasks.sqlite3")
    )
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        manager = service.tasks
        manager._register_worker_process("task-reaper", child)
        manager._release_worker_process("task-reaper", grace=0.1)
        assert manager._worker_processes == {}
        # The child is still alive: shutdown releases the handle, it never kills.
        assert child.poll() is None
    finally:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)
        service.shutdown()
