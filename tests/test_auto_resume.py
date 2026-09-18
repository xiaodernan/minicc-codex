"""Auto-resume-on-start tests (daemonization step 1)."""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from minicc.task_store import TaskStore
from minicc.web import AgentService


def _snapshot(tmp_path: Path, task_id: str) -> dict:
    return {
        "task_id": task_id,
        "session_id": "web-latest",
        "created_at_epoch": time.time(),
        "created_at": "2026-09-13T00:00:00Z",
        "workspace_path": str(tmp_path),
        "status": "running",  # becomes "interrupted" on restore
        "prompt": "重启前正在运行的任务",
        "preview": "重启前正在运行的任务",
        "allow_changes": False,
        "allow_network": False,
        "stream_text": "",
        "events": [],
    }


def _service(tmp_path: Path, *, auto_resume: bool, store: TaskStore) -> AgentService:
    config = SimpleNamespace(
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
        auto_resume_on_start=auto_resume,
    )
    return AgentService(tmp_path, config, task_store=store)


@pytest.fixture()
def fake_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from minicc import web as web_module

    class FakeProvider:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def chat(self, messages, tools, on_delta=None):
            import json as _json
            import re

            from minicc.llm.base import LLMResponse

            if tools is None:
                decision = _json.dumps({
                    "status": "complete", "confidence": 0.9, "rationale": "fake",
                    "missing": [], "next_action": "", "evidence": re.findall(r'"id":"((?:event|verification)-\d+)"', str(messages))[-1:],
                }, ensure_ascii=False)
                return LLMResponse(content=decision)
            return LLMResponse(content="恢复后的任务已完成。")

        async def close(self):
            return None

    monkeypatch.setattr(web_module, "OpenAICompatibleProvider", FakeProvider)


def test_store_without_flag_keeps_interrupted(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.sqlite3")
    store.upsert(_snapshot(tmp_path, "task-interrupted-1"))
    service = _service(tmp_path, auto_resume=False, store=store)
    try:
        assert service.tasks.get("task-interrupted-1")["status"] == "interrupted"
    finally:
        service.shutdown()


def test_store_with_flag_requeues_interrupted(tmp_path: Path, fake_provider: None) -> None:
    store = TaskStore(tmp_path / "tasks.sqlite3")
    store.upsert(_snapshot(tmp_path, "task-interrupted-2"))
    service = _service(tmp_path, auto_resume=True, store=store)
    try:
        # Auto-resume keeps the interrupted record for audit and re-queues the
        # work as a NEW task; the resumed copy must not stay interrupted.
        statuses = [record.status for record in service.tasks.tasks.values()]
        assert len(service.tasks.tasks) >= 2
        assert any(status in {"queued", "running", "completed"} for status in statuses)
    finally:
        service.shutdown()
