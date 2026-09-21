"""会话核心测试：SessionStore 往返、多模态载荷、按会话串行与从 checkpoint 恢复。

M8-T6 拆分说明：测试本体逐字搬迁，未改断言。"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace
import pytest
from minicc.session import SessionStore
from minicc.tools.schemas import ToolCall, ToolResult
from minicc.web import TaskManager, TaskRecord, _multimodal_content
from minicc.main import CliView


def test_multimodal_content_keeps_text_and_image_parts() -> None:
    content = _multimodal_content(
        "请描述图片",
        [{"mime_type": "image/png", "data": b"png-bytes"}],
    )
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "请描述图片"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_task_snapshot_hides_attachment_payload_and_resume_reloads_it(tmp_path: Path) -> None:
    received: list[list[dict[str, object]]] = []

    class FakeService:
        config = SimpleNamespace(yolo=False, max_concurrent_tasks=1, model="test-model")
        workspace = tmp_path

        @staticmethod
        def _run_chat(payload, *, on_event=None, on_stream=None, cancel_event=None):
            received.append(payload.get("attachments") or [])
            return {"answer": "image inspected", "cancelled": False, "events": []}

    manager = TaskManager(FakeService(), max_workers=1)
    try:
        task = manager.submit({
            "message": "请分析图片",
            "session_id": "image-test",
            "attachments": [{
                "name": "screen.png",
                "mime_type": "image/png",
                "data_url": "data:image/png;base64,cG5nLWJ5dGVz",
            }],
        })
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and manager.get(task["task_id"])["status"] != "completed":
            time.sleep(0.01)
        snapshot = manager.get(task["task_id"])
        assert snapshot["status"] == "completed"
        assert snapshot["attachments"][0]["name"] == "screen.png"
        assert "data_url" not in snapshot["attachments"][0]
        assert received[0][0]["data_url"].startswith("data:image/png;base64,")

        resumed = manager.resume(task["task_id"])
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and manager.get(resumed["task_id"])["status"] != "completed":
            time.sleep(0.01)
        assert len(received) == 2
        assert received[1][0]["name"] == "screen.png"
    finally:
        manager.shutdown()


def test_session_round_trip_redacts_credentials(tmp_path: Path) -> None:
    store = SessionStore(tmp_path, "interview-1")
    store.save(
        [
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "token sk-secret-value"},
        ]
    )
    loaded = store.load("new rules")
    assert loaded[0]["content"] == "new rules"
    assert "sk-secret-value" not in store.path.read_text(encoding="utf-8")


def test_cli_view_persists_reading_anchor_and_compact_preference(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store = SessionStore(tmp_path, "cli-view")
    view = CliView(store)
    view.record_tool(
        ToolCall(tool="bash", arguments={"command": "echo sk-secret-value"}),
        ToolResult(status="ok", summary="命令完成", head="人类可读结果"),
    )
    view.record_answer()
    view.set_compact(False)

    restored = CliView(SessionStore(tmp_path, "cli-view"), announce_resume=True)
    assert restored.last_item == 2
    assert restored.last_tool == 1
    assert restored.compact_tools is False
    assert restored.tool_history[-1]["tool"] == "bash"
    assert "sk-secret-value" not in store.path.read_text(encoding="utf-8")
    restored.expand()
    assert "人类可读结果" in capsys.readouterr().out


def test_interrupted_readonly_resume_continues_from_session_checkpoint(tmp_path: Path) -> None:
    (tmp_path / "evidence.txt").write_text("stable\n", encoding="utf-8")
    observed_payloads: list[dict[str, object]] = []

    class FakeService:
        config = SimpleNamespace(yolo=False, max_concurrent_tasks=1, model="test-model")
        workspace = tmp_path

        @staticmethod
        def _run_chat(payload, *, on_event=None, on_stream=None, cancel_event=None):
            observed_payloads.append(payload)
            return {"answer": "从会话检查点继续完成", "cancelled": False, "events": []}

    session = SessionStore(tmp_path, "interrupted-session")
    session.save([
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "原始检查请求"},
        {"role": "assistant", "content": "已读取 evidence.txt"},
    ])
    manager = TaskManager(FakeService(), max_workers=1)
    source = TaskRecord(
        task_id="task-interrupted",
        session_id="interrupted-session",
        message="原始检查请求",
        allow_changes=False,
        workspace_path=str(tmp_path),
        status="interrupted",
        phase="interrupted",
        checkpoint={
            "paths": ["evidence.txt"],
            "workspace_digest": TaskManager._workspace_checkpoint_digest(tmp_path, ["evidence.txt"]),
            "safe_readonly": True,
        },
    )
    manager.tasks[source.task_id] = source
    try:
        resumed = manager.resume(source.task_id)
        assert resumed["context"]["recovery"]["mode"] == "session_checkpoint"
        assert resumed["context"]["recovery"]["resume_session"] is True
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not observed_payloads:
            time.sleep(0.01)
        assert observed_payloads
        assert observed_payloads[0]["resume_from_checkpoint"] is True
        assert str(observed_payloads[0]["message"]).startswith("[任务恢复]")
        assert "原始检查请求" not in str(observed_payloads[0]["message"])
    finally:
        manager.shutdown()


def test_task_manager_runs_different_sessions_without_blocking() -> None:
    entered = {"one": threading.Event(), "two": threading.Event()}
    release = threading.Event()

    class FakeService:
        config = SimpleNamespace(yolo=False, max_concurrent_tasks=2, model="test-model")
        workspace = Path.cwd()

        @staticmethod
        def _run_chat(payload, *, on_event=None, on_stream=None, cancel_event=None):
            session = payload["session_id"]
            entered[session].set()
            release.wait(2)
            return {"answer": session, "cancelled": False, "events": []}

    manager = TaskManager(FakeService(), max_workers=2)
    try:
        first = manager.submit({"message": "one", "session_id": "one"})
        second = manager.submit({"message": "two", "session_id": "two"})
        assert entered["one"].wait(1)
        assert entered["two"].wait(1)
        release.set()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if all(manager.get(item["task_id"])["status"] == "completed" for item in (first, second)):
                break
            time.sleep(0.01)
        assert manager.get(first["task_id"])["status"] == "completed"
        assert manager.get(second["task_id"])["status"] == "completed"
    finally:
        release.set()
        manager.shutdown()


def test_task_manager_queues_same_session_but_runs_other_sessions_in_parallel() -> None:
    entered: list[str] = []
    first_started = threading.Event()
    release = threading.Event()

    class FakeService:
        config = SimpleNamespace(yolo=False, max_concurrent_tasks=2, model="test-model")
        workspace = Path.cwd()

        @staticmethod
        def _run_chat(payload, *, on_event=None, on_stream=None, cancel_event=None):
            session = str(payload["session_id"])
            entered.append(str(payload["message"]))
            if payload["message"] == "same-1":
                first_started.set()
                release.wait(2)
            return {"answer": session, "cancelled": False, "events": []}

    manager = TaskManager(FakeService(), max_workers=2)
    try:
        first = manager.submit({"message": "same-1", "session_id": "same"})
        assert first_started.wait(1)
        second = manager.submit({"message": "same-2", "session_id": "same"})
        other = manager.submit({"message": "other", "session_id": "other"})
        assert manager.get(second["task_id"])["status"] == "queued"
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and "other" not in entered:
            time.sleep(0.01)
        assert "other" in entered
        assert "same-2" not in entered
        release.set()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if all(manager.get(item["task_id"])["status"] == "completed" for item in (first, second, other)):
                break
            time.sleep(0.01)
        assert [manager.get(item["task_id"])["status"] for item in (first, second, other)] == ["completed"] * 3
        assert entered.index("same-1") < entered.index("same-2")
    finally:
        release.set()
        manager.shutdown()


def test_task_manager_cancel_queued_same_session_wakes_next_task() -> None:
    entered = threading.Event()
    release = threading.Event()
    executed: list[str] = []

    class FakeService:
        config = SimpleNamespace(yolo=False, max_concurrent_tasks=1, model="test-model")
        workspace = Path.cwd()

        @staticmethod
        def _run_chat(payload, *, on_event=None, on_stream=None, cancel_event=None):
            message = str(payload["message"])
            executed.append(message)
            if message == "first":
                entered.set()
                release.wait(2)
            return {"answer": message, "cancelled": False, "events": []}

    manager = TaskManager(FakeService(), max_workers=1)
    try:
        first = manager.submit({"message": "first", "session_id": "cancel-queue"})
        assert entered.wait(1)
        cancelled = manager.submit({"message": "cancel-me", "session_id": "cancel-queue"})
        assert manager.get(cancelled["task_id"])["status"] == "queued"
        manager.cancel(cancelled["task_id"])
        assert manager.get(cancelled["task_id"])["status"] == "cancelled"
        next_task = manager.submit({"message": "next", "session_id": "cancel-queue"})
        release.set()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if manager.get(next_task["task_id"])["status"] == "completed":
                break
            time.sleep(0.01)
        assert manager.get(first["task_id"])["status"] == "completed"
        assert manager.get(next_task["task_id"])["status"] == "completed"
        assert "cancel-me" not in executed
        assert executed[-1] == "next"
    finally:
        release.set()
        manager.shutdown()
