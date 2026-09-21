"""Focused contracts for detached recovery, streaming, and background storage."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from minicc.task_contract import TaskRequest, TaskResult
from minicc.task_execution import WorkerSnapshotMirror, has_live_worker
from minicc.task_manager import TaskManager, TaskRecord
from minicc.task_store import TaskStore


def _task(workspace: Path, task_id: str = "task-contract") -> TaskRecord:
    return TaskRecord(task_id, "test-session", "inspect source", False, workspace_path=str(workspace))


def test_lease_has_single_owner_and_can_recover_after_expiry(tmp_path: Path) -> None:
    path = tmp_path / "tasks.sqlite3"
    stores = [TaskStore(path), TaskStore(path)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(store.claim_lease, "task", f"owner-{index}") for index, store in enumerate(stores)]
        claimed = [future.result() for future in futures]
    assert sum(claimed) == 1
    owner = f"owner-{claimed.index(True)}"
    assert not stores[0].heartbeat_lease("task", "wrong-owner", pid=1)
    stores[0].release_lease("task", "wrong-owner")
    assert stores[1].get_lease("task")["owner"] == owner
    assert stores[0].heartbeat_lease("task", owner, pid=1, ttl=-1)
    assert stores[1].claim_lease("task", "replacement")
    assert not stores[0].heartbeat_lease("task", owner, pid=1)
    snapshot = {"task_id": "task", "prompt": "result", "status": "completed"}
    assert not stores[0].upsert(snapshot, lease_owner=owner)
    assert stores[0].get("task") is None
    assert stores[1].upsert(snapshot, lease_owner="replacement")


def test_expired_lease_cannot_be_revived_by_same_owner(tmp_path: Path) -> None:
    """M3-T5: a late heartbeat must not extend an already-expired lease.

    The owner's heartbeat UPDATE lacked the `expires > now` fence, so a
    frozen worker revived its own lease forever, has_live_worker kept
    reporting it alive, and auto-resume refused to re-queue the task.
    """
    store = TaskStore(tmp_path / "tasks.sqlite3")
    assert store.claim_lease("task", "owner-a", pid=1)
    # Force expiry: negative ttl writes expires into the past.
    assert store.heartbeat_lease("task", "owner-a", pid=1, ttl=-1)
    # Same owner, expired lease: the heartbeat must now fail.
    assert not store.heartbeat_lease("task", "owner-a", pid=1)
    assert not has_live_worker(store, {"task_id": "task", "status": "running"})
    # The abandoned lease is claimable and the new owner can heartbeat.
    assert store.claim_lease("task", "owner-b", pid=2)
    assert store.heartbeat_lease("task", "owner-b", pid=2)


def test_mirror_continues_after_retained_window_and_deduplicates(tmp_path: Path) -> None:
    task = _task(tmp_path)
    task.transition_status("running")
    mirror = WorkerSnapshotMirror(task)
    text = "a" * 16000
    event = {"event_id": "evt-stable", "name": "read_file", "path": "test.py", "status": "ok"}
    mirror.apply({"stream_text": text, "stream_length": 16000, "events": [event]})
    mirror.apply({"stream_text": text[100:] + "b" * 100, "stream_length": 16100, "events": [event]})
    assert task.stream_length == 16100
    assert task.stream_text.endswith("b" * 100)
    assert len(task.events) == 1
    # The reader was detached for longer than a complete retained window.
    mirror.apply({"stream_text": "c" * 16000, "stream_length": 50000})
    assert task.stream_text == "c" * 16000
    assert task.stream_length == 50000
    mirror.apply({"usage": {"total_tokens": 10}})
    mirror.apply({"usage": {"total_tokens": 20}})
    assert task.tokens_used["total_tokens"] == 20
    mirror.apply({"stream_text": "old", "stream_length": 10})
    assert task.stream_length == 50000


def test_execution_request_preserves_permissions_and_attachments(tmp_path: Path) -> None:
    manager = TaskManager(SimpleNamespace(config=SimpleNamespace(yolo=False), workspace=tmp_path))
    try:
        task = _task(tmp_path)
        task.permission_mode = "acceptEdits"
        task.reasoning_effort = "max"
        task.context["recovery"] = {"resume_session": True}
        task.attachments = [{"name": "screen.png", "mime_type": "image/png", "data": b"image"}]
        manager._load_attachment_payloads = lambda record: record.attachments
        request = manager._execution_request(task)
        roundtrip = TaskRequest.from_payload(json.loads(json.dumps(request.to_payload())))
        assert roundtrip.permission_mode == "acceptEdits"
        assert roundtrip.task_id == task.task_id
        assert roundtrip.reasoning_effort == "max"
        assert roundtrip.resume_from_checkpoint
        assert roundtrip.attachments[0]["data_url"] == "data:image/png;base64,aW1hZ2U="
    finally:
        manager.shutdown()


def test_result_contract_preserves_verification_and_normalizes_both_executors() -> None:
    raw = {"answer": "done", "tokens_used": {"total_tokens": 5}, "verification_results": [{"status": "passed"}]}
    normalized = TaskResult.from_payload(raw).to_payload()
    assert WorkerSnapshotMirror.result({"status": "completed", "result": raw, "usage": raw["tokens_used"]}) == normalized
    assert normalized["verification_results"] == raw["verification_results"]
    assert WorkerSnapshotMirror.result({"status": "interrupted"})["error"]


def test_readonly_task_starts_without_copying_workspace_snapshot(tmp_path, monkeypatch):
    called = threading.Event()
    def capture(*args): raise AssertionError("readonly task must not copy workspace files")
    def run(payload, **kwargs):
        called.set()
        return {"answer": "read-only summary", "events": []}
    monkeypatch.setattr("minicc.snapshots.capture", capture)
    service = SimpleNamespace(config=SimpleNamespace(yolo=False, model="test-model"), workspace=tmp_path, _run_chat=run)
    manager = TaskManager(service)
    try:
        result = manager.submit({"message": "inspect", "permission_mode": "plan", "allow_changes": True})
        assert called.wait(1)
        task = manager.tasks[result["task_id"]]
        task.future.result(timeout=3)
        assert task.checkpoint["workspace_snapshot"] == {"captured": False, "reason": "readonly_task"}
    finally:
        manager.shutdown()


def test_restart_reconnects_without_rewriting_live_worker(tmp_path: Path, monkeypatch) -> None:
    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = _task(tmp_path)
    task.transition_status("running")
    original = {**task.snapshot(), "worker_version": 2, "heartbeat_at_epoch": time.time()}
    store.upsert(original)
    store.claim_lease(task.task_id, "live-worker")
    reconnected = threading.Event()
    monkeypatch.setattr(TaskManager, "_reconnect_worker", lambda self, record: reconnected.set())
    service = SimpleNamespace(config=SimpleNamespace(yolo=False, auto_resume_on_start=True), workspace=tmp_path)
    manager = TaskManager(service, store=store)
    try:
        assert reconnected.wait(2)
        assert manager.get(task.task_id)["status"] == "running"
        assert store.get(task.task_id)["status"] == "running"
        assert len(manager.tasks) == 1
    finally:
        manager.shutdown()
    assert store.get(task.task_id)["status"] == "running"


def test_sqlite_write_does_not_block_stream_callbacks_and_final_wins(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.sqlite3")
    manager = TaskManager(SimpleNamespace(config=SimpleNamespace(yolo=False), workspace=tmp_path), store=store)
    task = _task(tmp_path)
    task.transition_status("running")
    entered = threading.Event()
    release = threading.Event()
    actual_upsert = store.upsert

    def slow_write(snapshot):
        if snapshot["status"] == "running":
            entered.set()
            assert release.wait(4)
        actual_upsert(snapshot)

    store.upsert = slow_write
    try:
        task.append_stream("first")
        manager._persist_task(task)
        assert entered.wait(2)
        callback_completed = threading.Event()

        def append_more():
            task.append_stream("-second")
            manager._persist_task(task)
            callback_completed.set()

        callback = threading.Thread(target=append_more)
        callback.start()
        assert callback_completed.wait(0.5), "disk writer holds the callback state lock"
        task.transition_status("completed")
        release.set()
        manager._persist_task(task, force=True)
        callback.join(2)
        stored = store.get(task.task_id)
        assert stored["status"] == "completed"
        assert stored["stream_text"] == "first-second"
    finally:
        release.set()
        manager.shutdown()


def test_history_projection_migrates_unicode_and_ignores_event_payload(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE tasks(task_id TEXT PRIMARY KEY, created_at REAL NOT NULL, workspace_path TEXT NOT NULL, payload TEXT NOT NULL)")
        snapshot = {"task_id": "task-old", "created_at_epoch": 1, "workspace_path": "workspace-a", "prompt": "Straße 正确文本", "status": "completed", "events": [{"output": "metadata-only needle"}]}
        connection.execute("INSERT INTO tasks VALUES (?, ?, ?, ?)", ("task-old", 1, "workspace-a", json.dumps(snapshot)))
    store = TaskStore(path)
    assert [item["task_id"] for item in store.search("STRASSE")] == ["task-old"]
    assert "Straße" in store.search("strasse")[0]["snippet"]
    assert store.search("metadata-only") == []
    assert store.search("正确", workspace_path="workspace-b") == []
    store.upsert({**snapshot, "prompt": "new visible text"})
    assert store.search("STRASSE") == []
    assert store.search("visible")
    store.prune(keep_terminal=0)
    assert store.search("visible") == []
