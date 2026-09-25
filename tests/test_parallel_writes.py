"""M6-T3: independent file writes fan out; same-path writes stay ordered.

These assert the executor's write phase directly (the mechanism ``run_agent``
calls once per tool round), which is where the wall-clock win and the ordering
guarantees live:

- four writes to *different* paths run concurrently (proven by an in-flight
  counter, not by a stopwatch: see ``test_parallel_writes_are_actually_overlapping``);
- two edits to the *same* path stay serialized so the second observes the first;
- one failing write does not lose the results of its concurrent siblings;
- non-write tools (bash) never run alongside a concurrent edit.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

from minicc.agent.loop import _parallel_write_key, _run_write_phase
from minicc.tools.registry import Param, ToolRegistry, ToolSpec
from minicc.tools.schemas import ToolCall, ToolResult


def _param(name: str) -> Param:
    return Param(name, "str", required=True)


def _write_registry(sleep: float, events: list[str], failures: set[str]) -> ToolRegistry:
    """A registry whose ``write_file``/``edit_file`` handlers observe timing."""

    def make(tool_name: str):
        def handler(args: dict[str, Any]) -> ToolResult:
            path = str(args["path"])
            events.append(f"start:{tool_name}:{path}")
            time.sleep(sleep)
            if path in failures:
                events.append(f"fail:{path}")
                return ToolResult(status="error", summary=f"[ERR] {path}", security_tags=["untrusted"])
            events.append(f"end:{tool_name}:{path}")
            return ToolResult(status="ok", summary=f"ok {path}", data={"path": path})

        return handler

    registry = ToolRegistry()
    registry.register(ToolSpec("write_file", "w", "write", (_param("path"),), make("write_file")))
    registry.register(ToolSpec("edit_file", "e", "write", (_param("path"),), make("edit_file")))
    return registry


def _max_in_flight(events: list[str]) -> int:
    """Peak number of writes open at the same instant, read off the event log."""

    inflight = peak = 0
    for event in events:
        if event.startswith("start:"):
            inflight += 1
            peak = max(peak, inflight)
        elif event.startswith(("end:", "fail:")):
            inflight -= 1
    assert inflight == 0, events  # every open window was closed
    return peak


def _call(tool: str, path: str) -> ToolCall:
    return ToolCall(tool=tool, arguments={"path": path}, call_id=path)


def _store(index: int, call: ToolCall) -> tuple[int, ToolCall, str]:
    return (index, call, _parallel_write_key(call.tool, call.arguments))


def test_four_distinct_path_writes_run_in_parallel() -> None:
    events: list[str] = []
    registry = _write_registry(0.3, events, failures=set())
    immediate: dict[int, tuple[ToolCall, ToolResult]] = {}
    pending = [_store(i, _call("write_file", f"f{i}.py")) for i in range(4)]

    started = time.monotonic()
    asyncio.run(_run_write_phase(
        registry=registry, pending_writes=pending, serial_writes=[],
        immediate_results=immediate, cancel_event=None,
    ))
    elapsed = time.monotonic() - started

    # The concurrency claim lives in `_max_in_flight` below and in
    # `test_parallel_writes_are_actually_overlapping`; a stopwatch that turns red
    # after 0.3s of scheduler hiccup measures the machine, not this code.  What a
    # timer is still good for is the one thing it can decide honestly: it finished.
    assert elapsed < 15.0, f"write phase took {elapsed:.2f}s; it should not hang"
    assert _max_in_flight(events) >= 2, events
    assert len(immediate) == 4
    assert all(result.status == "ok" for _tc, result in immediate.values())


def test_same_path_edits_stay_serial_and_ordered() -> None:
    events: list[str] = []
    registry = _write_registry(0.15, events, failures=set())
    immediate: dict[int, tuple[ToolCall, ToolResult]] = {}
    # Two edits to the SAME path share one key → one serial group.
    pending = [
        _store(0, _call("edit_file", "shared.py")),
        _store(1, _call("edit_file", "shared.py")),
    ]

    asyncio.run(_run_write_phase(
        registry=registry, pending_writes=pending, serial_writes=[],
        immediate_results=immediate, cancel_event=None,
    ))

    shared = [e for e in events if "shared.py" in e]
    # Serialized: start,end,start,end — not start,start,end,end (overlap).
    assert shared == [
        "start:edit_file:shared.py", "end:edit_file:shared.py",
        "start:edit_file:shared.py", "end:edit_file:shared.py",
    ]
    assert immediate[0][1].status == "ok" and immediate[1][1].status == "ok"


def test_one_failing_write_does_not_lose_the_others() -> None:
    events: list[str] = []
    registry = _write_registry(0.05, events, failures={"bad.py"})
    immediate: dict[int, tuple[ToolCall, ToolResult]] = {}
    pending = [
        _store(0, _call("write_file", "a.py")),
        _store(1, _call("write_file", "bad.py")),
        _store(2, _call("write_file", "c.py")),
    ]

    asyncio.run(_run_write_phase(
        registry=registry, pending_writes=pending, serial_writes=[],
        immediate_results=immediate, cancel_event=None,
    ))

    assert len(immediate) == 3
    assert immediate[1][1].status == "error"
    assert immediate[0][1].status == "ok"
    assert immediate[2][1].status == "ok"


def test_non_write_tools_run_as_a_serial_group() -> None:
    # A bash-style tool (no path key) must never join the concurrent set.
    assert _parallel_write_key("bash", {"command": "ls"}) is None
    assert _parallel_write_key("write_file", {"path": ""}) is None
    assert _parallel_write_key("write_file", "not-a-dict") is None


def test_parallel_writes_are_actually_overlapping() -> None:
    # Guard against a silent regression back to serial: the two writes' active
    # windows must overlap in wall time, proven by a concurrency counter.
    peak = {"n": 0}
    lock = threading.Lock()
    active = {"n": 0}

    def handler(args: dict[str, Any]) -> ToolResult:
        with lock:
            active["n"] += 1
            peak["n"] = max(peak["n"], active["n"])
        time.sleep(0.2)
        with lock:
            active["n"] -= 1
        return ToolResult(status="ok", summary="ok")

    registry = ToolRegistry()
    registry.register(ToolSpec("write_file", "w", "write", (_param("path"),), handler))
    immediate: dict[int, tuple[ToolCall, ToolResult]] = {}
    pending = [_store(i, _call("write_file", f"p{i}.py")) for i in range(3)]

    asyncio.run(_run_write_phase(
        registry=registry, pending_writes=pending, serial_writes=[],
        immediate_results=immediate, cancel_event=None,
    ))
    assert peak["n"] >= 2, "writes did not overlap — still serialized?"
