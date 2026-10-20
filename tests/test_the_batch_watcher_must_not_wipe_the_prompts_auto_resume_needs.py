"""M8-T269: the batch watcher must not wipe the prompts auto-resume needs.

``TaskRecord.update_context`` *replaces* the context.  That is the right
meaning for the agent loop's own context callback, but the batch watcher used
it to publish three counters - and the replace dropped everything else the
parent was carrying, including ``batch_messages``: the raw subtask prompts
that ``resume()`` needs to rebuild an interrupted batch exactly.

So the guarantee M3-T9 put in place ("an interrupted batch can be
reconstructed exactly on auto-resume") was undone the first time the watcher
ticked.  The count reached the store and the prompts did not.

This door pins:

* the watcher updates its counters *and* leaves the prompts in place;
* the prompts survive in the persisted snapshot, not just in memory;
* the controls: the counters still move, and a plain (non-batch) context
  replacement still replaces.
"""

from __future__ import annotations

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


def test_the_watcher_leaves_the_subtask_prompts_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = TaskStore(tmp_path / "tasks.sqlite3")
    service = _service(tmp_path, store)
    try:
        monkeypatch.setattr(service.tasks, "_start_batch", lambda parent_id: None)
        # The watcher's tail hands the parent to the model (auto mode) or to
        # the merge face.  Neither belongs to this door, and both would reach
        # for the network - so they are stubbed out here.
        monkeypatch.setattr(service.tasks, "_run", lambda parent: None)
        monkeypatch.setattr(
            service, "merge_batch", lambda children, **kwargs: {"answer": "merged"}
        )
        prompts = [f"子任务提示词 {i}" for i in range(4)]
        created = service.tasks.submit_batch({
            "messages": prompts,
            "session_id": "batch-watcher",
            "workspace_path": str(tmp_path),
            "allow_changes": False,
        })
        parent_id = created["task_id"]
        parent = service.tasks.tasks[parent_id]

        # The children are terminal, so the watcher publishes its counters
        # once and returns - the tick that used to wipe the context.
        for child_id in parent.child_task_ids:
            service.tasks.tasks[child_id].status = "completed"

        # One tick of the *real* watcher, not a hand-rolled context write:
        # the whole point is which method the watcher itself reaches for.
        service.tasks._watch_batch(parent, list(parent.child_task_ids))

        assert parent.context.get("batch_messages") == prompts, (
            "the watcher dropped the subtask prompts it has no business knowing about"
        )
        assert parent.context.get("children_total") == len(prompts)
        assert parent.context.get("children_completed") == len(prompts)
    finally:
        service.shutdown()


def test_the_prompts_survive_in_the_persisted_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store is what auto-resume reads; the in-memory copy is not enough."""
    store = TaskStore(tmp_path / "tasks.sqlite3")
    service = _service(tmp_path, store)
    try:
        monkeypatch.setattr(service.tasks, "_start_batch", lambda parent_id: None)
        prompts = [f"子任务提示词 {i}" for i in range(3)]
        created = service.tasks.submit_batch({
            "messages": prompts,
            "session_id": "batch-persist",
            "workspace_path": str(tmp_path),
            "allow_changes": False,
        })
        parent_id = created["task_id"]
        parent = service.tasks.tasks[parent_id]

        parent.merge_context({"children_completed": 1, "children_total": 3, "tokens": 7})
        service.tasks._persist_task(parent, force=True)

        stored = store.get(parent_id)
        assert stored is not None
        assert (stored.get("context") or {}).get("batch_messages") == prompts
    finally:
        service.shutdown()


def test_a_plain_context_replacement_still_replaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: the two methods mean different things on purpose."""
    store = TaskStore(tmp_path / "tasks.sqlite3")
    service = _service(tmp_path, store)
    try:
        monkeypatch.setattr(service.tasks, "_start_batch", lambda parent_id: None)
        created = service.tasks.submit_batch({
            "messages": ["子任务一"],
            "session_id": "batch-replace",
            "workspace_path": str(tmp_path),
            "allow_changes": False,
        })
        parent = service.tasks.tasks[created["task_id"]]

        parent.update_context({"orchestration": {"kind": "fixed"}})
        assert parent.context == {"orchestration": {"kind": "fixed"}}
    finally:
        service.shutdown()


def test_merging_into_a_finished_task_is_a_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A terminal task must not be resurrected by a late watcher tick."""
    store = TaskStore(tmp_path / "tasks.sqlite3")
    service = _service(tmp_path, store)
    try:
        monkeypatch.setattr(service.tasks, "_start_batch", lambda parent_id: None)
        created = service.tasks.submit_batch({
            "messages": ["子任务一"],
            "session_id": "batch-terminal",
            "workspace_path": str(tmp_path),
            "allow_changes": False,
        })
        parent = service.tasks.tasks[created["task_id"]]
        before = dict(parent.context)
        parent.status = "completed"
        parent.merge_context({"children_completed": 99})
        assert parent.context == before
    finally:
        service.shutdown()
