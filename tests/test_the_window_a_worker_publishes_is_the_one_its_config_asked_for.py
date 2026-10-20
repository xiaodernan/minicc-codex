"""The task window a worker publishes must be the one its config asked for (M8-T268).

Measured on the pre-fix bytes (`mc-t268/probe_t268.py`), with the knobs published in
README.md:66-67 and minicc.config.example:156-157 set above the worker's constants:

```
leg1 config task_event_limit = 1000   worker EVENTS_BOUND = 200
   fed events=500 kept = 200            fed stream=40000 kept = 16000
   payload has event_limit / stream_limit / events_truncated = False False False
leg2 thread face kept 500 events, events_truncated=0, declared event_limit=1000
leg3 run_worker(task_event_limit=32) -> stored row has event_limit/stream_limit/
   events_truncated = False
```

so one config produced two histories (500 on the thread face, 200 on the process
face), and the row the process face wrote declared neither the window it applied
nor the events behind it - which left the restore path (task_manager.py:995-996,
:1019) announcing a 768-event window and `events_truncated = 0` for a row that a
constant had just cut to 200.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

from minicc import task_worker
from minicc.config import DEFAULT_TASK_EVENT_LIMIT, DEFAULT_TASK_STREAM_LIMIT
from minicc.task_manager import TaskRecord
from minicc.task_store import TaskStore


def _events(count: int) -> list[dict[str, object]]:
    return [{"kind": "tool_call", "event_id": f"evt-{i}", "sequence": i} for i in range(count)]


def _snap(events: list[dict[str, object]], *, stream_text: str = "", **overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "workspace": Path("."),
        "status": "running",
        "phase": "acting",
        "prompt": "p",
        "stream_text": stream_text,
        "events": list(events),
        "usage": None,
        "answer": "",
        "error": "",
        "allow_changes": False,
        "allow_network": False,
        "permission_mode": "ask",
        "session_id": "s",
    }
    kwargs.update(overrides)
    return task_worker._snapshot("task-window", **kwargs)  # type: ignore[arg-type]


def _config(event_limit: object = 768, stream_limit: object = 16_000) -> SimpleNamespace:
    return SimpleNamespace(task_event_limit=event_limit, task_stream_limit=stream_limit)


def _record(event_limit: int, stream_limit: int, events: list[dict[str, object]], *, stream_text: str = "") -> TaskRecord:
    return TaskRecord(
        task_id="task-thread",
        session_id="s",
        message="p",
        allow_changes=False,
        event_limit=event_limit,
        stream_limit=stream_limit,
        events=list(events),
        stream_text=stream_text,
    )


def test_the_worker_window_comes_from_the_config_it_was_handed() -> None:
    event_limit, stream_limit = task_worker._window_from(_config(1000, 40_000))
    assert (event_limit, stream_limit) == (1000, 40_000), (
        f"_window_from ignored the config and returned {(event_limit, stream_limit)}"
    )
    snap = _snap(_events(500), event_limit=event_limit, stream_limit=stream_limit)
    assert len(snap["events"]) == 500, (  # type: ignore[arg-type]
        f"config asked for a {event_limit}-event window but the worker kept {len(snap['events'])} of 500"  # type: ignore[arg-type]
    )


def test_the_worker_honours_a_window_smaller_than_the_published_default() -> None:
    snap = _snap(_events(500), event_limit=400, stream_limit=16_000)
    kept = snap["events"]
    assert len(kept) == 400, f"a 400-event window kept {len(kept)} (the old constant was 200)"  # type: ignore[arg-type]
    assert kept[0]["event_id"] == "evt-100", "the window must keep the newest events, not the oldest"  # type: ignore[index]


def test_a_config_without_the_knobs_falls_back_to_the_published_defaults() -> None:
    event_limit, stream_limit = task_worker._window_from(SimpleNamespace())
    assert (event_limit, stream_limit) == (DEFAULT_TASK_EVENT_LIMIT, DEFAULT_TASK_STREAM_LIMIT), (
        f"a config without the knobs fell back to {(event_limit, stream_limit)}, "
        f"not to the published defaults {(DEFAULT_TASK_EVENT_LIMIT, DEFAULT_TASK_STREAM_LIMIT)}"
    )
    snap = _snap(_events(900))
    assert len(snap["events"]) == DEFAULT_TASK_EVENT_LIMIT, (  # type: ignore[arg-type]
        f"the snapshot builder defaulted to {len(snap['events'])} events, "  # type: ignore[arg-type]
        f"not to the published DEFAULT_TASK_EVENT_LIMIT={DEFAULT_TASK_EVENT_LIMIT}"
    )


def test_a_window_below_the_published_floor_still_keeps_the_floor() -> None:
    worker_event_limit, worker_stream_limit = task_worker._window_from(_config(1, 1))
    record = _record(1, 1, _events(40))
    assert (worker_event_limit, worker_stream_limit) == (record.event_limit, record.stream_limit), (
        f"the worker floors the window at {(worker_event_limit, worker_stream_limit)} "
        f"while the thread face floors it at {(record.event_limit, record.stream_limit)}"
    )
    snap = _snap(_events(40), event_limit=worker_event_limit, stream_limit=worker_stream_limit)
    assert len(snap["events"]) == record.event_limit, (  # type: ignore[arg-type]
        f"the two faces kept different counts for a below-floor window: "
        f"worker {len(snap['events'])} (type {type(snap['events']).__name__}), thread {len(record.events)}"  # type: ignore[arg-type]
    )


def test_the_worker_and_the_thread_face_keep_the_same_events_for_one_config() -> None:
    events = _events(500)
    record = _record(400, 16_000, events)
    snap = _snap(events, event_limit=400, stream_limit=16_000)
    assert len(snap["events"]) == len(record.events), (  # type: ignore[arg-type]
        f"one config, two histories: the thread face kept {len(record.events)} events "  # type: ignore[arg-type]
        f"and the worker kept {len(snap['events'])}"
    )
    assert snap["events_truncated"] == record.events_truncated, (
        f"the two faces report different drop counts: worker {snap['events_truncated']!r}, "
        f"thread {record.events_truncated!r}"
    )


def test_the_events_the_worker_drops_are_counted_where_they_happen() -> None:
    snap = _snap(_events(500), event_limit=400, stream_limit=16_000)
    assert len(snap["events"]) == 400, f"window 400 kept {len(snap['events'])}"  # type: ignore[arg-type]
    assert snap["events_truncated"] == 100, (
        f"500 events in, 400 retained, so the row must disclose 100 dropped - got {snap['events_truncated']!r}"
    )
    live = _snap(_events(500), event_limit=400, stream_limit=16_000, events_truncated=5)
    assert live["events_truncated"] == 105, (
        f"the snapshot must add its own residue to what the live path already evicted, got {live['events_truncated']!r}"
    )


def test_the_stream_window_is_the_configured_one_too() -> None:
    snap = _snap(_events(1), stream_text="x" * 40_000, event_limit=768, stream_limit=5000)
    assert len(snap["stream_text"]) == 5000, (  # type: ignore[arg-type]
        f"MINICC_TASK_STREAM_LIMIT=5000 cut the stream to {len(snap['stream_text'])} chars "  # type: ignore[arg-type]
        f"on the worker face (the old constant was 16000)"
    )
    assert snap["stream_length"] == 40_000, "the total stream length must survive the cut"


def test_the_row_the_worker_writes_declares_the_window_it_applied() -> None:
    snap = _snap(_events(100), event_limit=300, stream_limit=4000)
    assert snap["event_limit"] == 300, (
        f"the row declared its window as {snap['event_limit']!r}; the window was 300 and only "
        f"{len(snap['events'])} events happened to be in hand"  # type: ignore[arg-type]
    )
    assert snap["stream_limit"] == 4000, f"the row declared stream_limit={snap['stream_limit']!r}, expected 4000"
    assert snap["events_truncated"] == 0, "nothing fell out, so the row must not invent drops"


def test_a_restored_record_does_not_claim_a_window_the_writer_never_applied() -> None:
    snap = _snap(_events(100), event_limit=32, stream_limit=512)
    record = TaskRecord.from_snapshot({**snap, "task_id": "task-restored", "created_at_epoch": time.time()})
    assert record.event_limit == 32, (
        f"a row written with a 32-event window restored as a {record.event_limit}-event window "
        f"because the writer declared none"
    )
    assert record.stream_limit == 512, f"restored stream_limit={record.stream_limit!r}, the writer used 512"


def test_the_live_append_helper_trims_and_reports_what_it_evicted() -> None:
    items: list[dict[str, object]] = []
    evicted = 0
    for event in _events(40):
        evicted += task_worker.append_bounded(items, dict(event), 32)
    assert len(items) == 32, f"a 32-event window holds {len(items)}"
    assert evicted == 8, f"the helper evicted {evicted} events, so the live count must be 8"
    assert items[-1]["event_id"] == "evt-39", "the newest event must survive the trim"  # type: ignore[index]


def test_the_worker_run_still_publishes_the_total_stream_length() -> None:
    snap = _snap(_events(3), stream_text="y" * 10_000)
    assert snap["stream_length"] == 10_000, (
        f"the total stream length is what the user reads as progress; got {snap['stream_length']!r}"
    )
    assert len(snap["stream_text"]) == 10_000, f"10000 chars under the default window must survive, got {len(snap['stream_text'])}"  # type: ignore[arg-type]


def test_the_two_faces_still_agree_when_the_knob_moves() -> None:
    events = _events(1000)
    for knob in (32, 400, 900):
        event_limit, stream_limit = task_worker._window_from(_config(knob, 16_000))
        record = _record(knob, 16_000, events)
        snap = _snap(events, event_limit=event_limit, stream_limit=stream_limit)
        assert len(snap["events"]) == len(record.events), (
            f"MINICC_TASK_EVENT_LIMIT={knob}: thread face kept {len(record.events)} events, "  # type: ignore[arg-type]
            f"worker face kept {len(snap['events'])}"  # type: ignore[arg-type]
        )
        assert snap["events_truncated"] == record.events_truncated, (
            f"MINICC_TASK_EVENT_LIMIT={knob}: the faces disclose different drop counts "
            f"({snap['events_truncated']!r} vs {record.events_truncated!r})"
        )


def test_the_stored_row_of_a_real_worker_run_declares_its_window(tmp_path: Path) -> None:
    store_path = tmp_path / "tasks.sqlite3"
    store = TaskStore(store_path)
    store.upsert({
        "task_id": "task-window-e2e", "prompt": "hi", "status": "queued",
        "created_at_epoch": time.time(), "session_id": "window",
    })
    config = {
        "yolo": True, "max_concurrent_tasks": 2, "sandbox_mode": "host",
        "sandbox_image": "python:3.11-slim", "base_url": "https://example.test/v1",
        "api_key": "k", "model": "m", "timeout": 10, "tool_mode": "auto",
        "reasoning_effort": "high", "max_turns": 2, "compact_threshold": 300000,
        "context_window_tokens": 300000, "task_event_limit": 32, "task_stream_limit": 512,
    }
    args = task_worker.build_parser().parse_args([
        "--workspace", str(tmp_path),
        "--task-id", "task-window-e2e",
        "--session-id", "window",
        "--message", "hi",
        "--store-path", str(store_path),
        "--config-json", json.dumps(config),
        "--fake-provider",
    ])
    assert task_worker.run_worker(args) == 0, "the fake-provider worker run must reach a terminal state"
    row = store.get("task-window-e2e")
    assert row["status"] == "completed", f"the worker stored status {row['status']!r}"
    assert row.get("event_limit") == 32, (
        f"the config handed to the worker asked for a 32-event window; the row it wrote declares "
        f"{row.get('event_limit')!r} (row keys: {sorted(row)}), so the restore path falls back to "
        f"{DEFAULT_TASK_EVENT_LIMIT}"
    )
    assert row["stream_limit"] == 512, f"the row declares stream_limit={row.get('stream_limit')!r}, expected 512"
    assert isinstance(row["events_truncated"], int) and row["events_truncated"] == 0, (
        f"the row's drop count must be a derived integer, got {row.get('events_truncated')!r}"
    )
    assert len(row["events"]) <= 32, f"the row holds {len(row['events'])} events for a 32-event window"
