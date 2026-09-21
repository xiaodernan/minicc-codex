"""M3-T9: batch auto-resume keeps subtask prompts; attachments persist once.

Two batch defects are pinned here:

* ``resume()`` used to flatten a ``batch`` parent into a single ``task``,
  re-running only the generic parent message and losing every subtask prompt.
  It now rebuilds the batch via ``submit_batch`` from the prompts persisted in
  the parent context.
* Each subtask re-persisted the same attachment bytes under its own task_id
  (16 children x 12MB ~= 204MB per run). Children now reference the parent's
  single copy.
"""

from __future__ import annotations

import base64
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from minicc.task_store import TaskStore
from minicc.web import AgentService


def _service(tmp_path: Path, store: TaskStore) -> AgentService:
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
        auto_resume_on_start=False,
    )
    return AgentService(tmp_path, config, task_store=store)


def _png_data_url() -> str:
    raw = b"\x89PNG\r\n\x1a\n" + b"A" * 2048
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def test_resume_batch_preserves_all_subtask_prompts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = TaskStore(tmp_path / "tasks.sqlite3")
    service = _service(tmp_path, store)
    try:
        # Children are created but never executed; we only test reconstruction.
        monkeypatch.setattr(service.tasks, "_start_batch", lambda parent_id: None)
        prompts = [f"子任务提示词 {i}" for i in range(16)]
        created = service.tasks.submit_batch({
            "messages": prompts,
            "session_id": "batch-resume",
            "workspace_path": str(tmp_path),
            "allow_changes": False,
        })
        parent_id = created["task_id"]
        original = service.tasks.tasks[parent_id]
        # The raw prompts are persisted so the batch can be rebuilt exactly.
        assert original.context.get("batch_messages") == prompts

        original.status = "interrupted"
        resumed = service.tasks.resume(parent_id)
        new_parent_id = resumed["task_id"]
        assert new_parent_id != parent_id

        new_parent = service.tasks.tasks[new_parent_id]
        assert len(new_parent.child_task_ids) == 16
        child_messages = [
            service.tasks.tasks[cid].message for cid in new_parent.child_task_ids
        ]
        for prompt in prompts:
            assert any(prompt in message for message in child_messages), prompt
    finally:
        service.shutdown()


def test_batch_attachments_persisted_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = TaskStore(tmp_path / "tasks.sqlite3")
    service = _service(tmp_path, store)
    try:
        monkeypatch.setattr(service.tasks, "_start_batch", lambda parent_id: None)
        created = service.tasks.submit_batch({
            "messages": ["子任务一", "子任务二", "子任务三"],
            "session_id": "batch-attach",
            "workspace_path": str(tmp_path),
            "attachments": [
                {"name": "img.png", "mime_type": "image/png", "data_url": _png_data_url()}
            ],
        })
        parent_id = created["task_id"]
        parent = service.tasks.tasks[parent_id]

        attach_root = tmp_path / ".minicc" / "attachments"
        files = [p for p in attach_root.rglob("*") if p.is_file()]
        # Exactly one physical copy regardless of subtask count.
        assert len(files) == 1
        assert files[0].parent.name == parent_id

        # Every child references the parent's single copy (no own directory).
        for cid in parent.child_task_ids:
            child = service.tasks.tasks[cid]
            assert child.attachments
            for record in child.attachments:
                assert record["path"].startswith(f".minicc/attachments/{parent_id}/")
            assert not (attach_root / cid).exists()

        # The shared copy is still loadable from a child record.
        first_child = service.tasks.tasks[parent.child_task_ids[0]]
        payloads = service.tasks._load_attachment_payloads(first_child)
        assert len(payloads) == 1
        assert payloads[0]["name"] == "img.png"
    finally:
        service.shutdown()
