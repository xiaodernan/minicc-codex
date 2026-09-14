"""Detached task worker process tests (daemonization step 2)."""

from __future__ import annotations

import json
import subprocess
import sys
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
    assert "worker-fake-answer" in str((snapshot.get("result") or {}).get("answer"))
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
        assert "worker-fake-answer" in str(snapshot.get("answer") or snapshot.get("stream_text") or "")
        # The durable store holds the worker's own terminal snapshot too.
        stored = TaskStore(store_path).get(task_id)
        assert stored is not None and stored["status"] == "completed"
    finally:
        service.shutdown()
