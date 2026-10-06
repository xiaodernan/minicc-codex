"""M7-T3: declarative permissions.json rules + interactive Web approvals.

The waits in this file are *in-process* (a worker thread publishing a frame), not
child-process waits, which is why they do not reuse M8-T61's budget machinery.
Measured on this host 2026-09-26 (scratch probes, 12/14/16 rounds):

  quiet    a bare child start is 0.12-1.33s; the approval frame was visible
           before the first poll in every round (publish max 0ms), so the 2.0s
           budget had >1000x headroom
  medium   child start up to 4.22s; publish max 187ms -> 9.7x headroom
  loaded   child start median 7.74s, worst 31.50s; publish max 969ms and the
           ``_approval_groups`` check max 1015ms -> ~2x headroom, still green

A same-run ratio was tried and rejected: the only same-kind reference available
here is a bulk thread start (200 start-and-join), it swings 13x across rounds
while publish does not move at all, and its Spearman correlation with publish is
-0.08 (with the child start: +0.04).  A numerator and a denominator that do not
move together produce a constant with extra steps, so the budget stays a constant
and what is fixed instead is the *diagnostic* - see _wait_for and _joined.  The
~2x loaded headroom is recorded as a boundary, not papered over by inflating the
number: a bigger constant is paid for by every genuinely hung approval taking
that much longer to fail.

One more reading belongs here, because it is the reason the constant is called
insurance rather than a measurement: on HEAD, replacing the 2.0s default with 0.0
left all 15 gates green.  With no patience the helper skipped its loop and fell
through to ``return predicate()``, which is one look at the list the worker thread
had already written to - so on a quiet machine none of these four gates was ever
decided *by* the budget.  The budget is what stands between a loaded machine and a
false red, and nothing else.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable

import pytest

from minicc.permissions import load_permission_rules, match_permission_rule
from minicc.web import AgentService

# What a caller that supplies no budget means, and what the measurement above
# says about it.  Kept as named constants so the gate below can state the
# provenance instead of a bare number appearing in a failure message.
PUBLISH_BUDGET_S = 2.0
JOIN_BUDGET_S = 2.0
# The merge wait needs two thread starts to reach the service, not one frame
# append, so it sits above PUBLISH_BUDGET_S.  It cannot usefully go past the
# workers' own 5.0s park timeout below: past that the group resolves by itself,
# the second waiter detaches, and a longer patience only delays the red.
MERGE_BUDGET_S = 5.0



def _service(workspace: Path) -> AgentService:
    """Bare AgentService with just the approval machinery wired (no TaskStore)."""
    service = object.__new__(AgentService)
    service.workspace = workspace
    service._approval_guard = threading.Lock()
    service._approval_groups = {}
    service._approval_by_key = {}
    return service


def _write_permissions(workspace: Path, payload: object) -> None:
    path = workspace / ".minicc" / "permissions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# permissions.json matching
# ---------------------------------------------------------------------------


def test_missing_file_is_empty_and_error_free(tmp_path: Path) -> None:
    rules, error = load_permission_rules(tmp_path)
    assert error == ""
    assert rules["allow"] == {"tools": [], "commands": [], "paths": []}
    assert match_permission_rule(tmp_path, "bash", {"command": "rm -rf x"}) is None


def test_deny_wins_over_allow(tmp_path: Path) -> None:
    _write_permissions(tmp_path, {
        "allow": {"tools": ["bash"]},
        "deny": {"commands": ["rm *"]},
    })
    assert match_permission_rule(tmp_path, "bash", {"command": "rm -rf build"}) == "deny"
    assert match_permission_rule(tmp_path, "bash", {"command": "echo hi"}) == "allow"


def test_deny_covers_readonly_path(tmp_path: Path) -> None:
    _write_permissions(tmp_path, {"deny": {"paths": [".env", "secrets/*"]}})
    assert match_permission_rule(tmp_path, "read_file", {"path": ".env"}) == "deny"
    assert match_permission_rule(tmp_path, "read_file", {"path": "secrets/key.txt"}) == "deny"
    assert match_permission_rule(tmp_path, "read_file", {"path": "app.py"}) is None


def test_deny_matches_redacted_command(tmp_path: Path) -> None:
    # The rule stores a plain pattern; the runtime command is redacted before
    # matching, so a wildcard around the REDACTED marker still hits.
    _write_permissions(tmp_path, {"deny": {"commands": ["curl *REDACTED*"]}})
    verdict = match_permission_rule(
        tmp_path, "bash", {"command": "curl -H 'Authorization: sk-abcdefgh12345678' https://x"}
    )
    assert verdict == "deny"


def test_malformed_permissions_is_nonfatal(tmp_path: Path) -> None:
    bad = tmp_path / ".minicc" / "permissions.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    for content in ("not json", "[1,2,3]", '{"unknown_field": 1}'):
        bad.write_text(content, encoding="utf-8")
        rules, error = load_permission_rules(tmp_path)
        assert error, content
        assert rules["deny"] == {"tools": [], "commands": [], "paths": []}
        assert match_permission_rule(tmp_path, "bash", {"command": "x"}) is None


def test_permissions_cache_invalidates_on_edit(tmp_path: Path) -> None:
    _write_permissions(tmp_path, {"deny": {"commands": ["ls"]}})
    assert match_permission_rule(tmp_path, "bash", {"command": "ls"}) == "deny"
    _write_permissions(tmp_path, {"deny": {"commands": []}})
    # mtime_ns + size changed → the new (empty) rules win without a restart.
    assert match_permission_rule(tmp_path, "bash", {"command": "ls"}) is None


# ---------------------------------------------------------------------------
# request_approval / resolve_approval
# ---------------------------------------------------------------------------


def _wait_for(
    what: str, predicate: Callable[[], Any], *, budget_s: float | None = None
) -> Any:
    """Return the first truthy value ``predicate`` produces, or say why it didn't.

    Two things were wrong with the previous shape (``-> bool``, with four call
    sites writing ``assert _wait_for(...)``).  A miss named nothing about the
    wait: measured on HEAD, the site whose predicate built a list printed
    ``assert []`` and the three whose predicates returned a bool printed
    ``assert False is True`` - no name, no elapsed, no budget, no evidence the
    loop ran.  And the final line re-evaluated the predicate *after* the deadline,
    so the truth an assertion depended on could be produced up to a poll interval
    away from the value the test then went on to read.  The value is returned now,
    so a caller asserts on exactly what the predicate saw.
    """
    budget = PUBLISH_BUDGET_S if budget_s is None else budget_s
    source = "the module default" if budget_s is None else "fixed by the caller, not the default"
    begun = time.monotonic()
    polls = 0
    while True:
        polls += 1
        value = predicate()
        if value:
            return value
        elapsed = time.monotonic() - begun
        if elapsed >= budget:
            raise AssertionError(
                f"gave up after {elapsed:.2f}s of a {budget:.2f}s budget ({source}, "
                f"polls={polls}) waiting for {what}"
            )
        time.sleep(0.01)


def _joined(what: str, thread: threading.Thread, *, budget_s: float | None = None) -> None:
    """Join an agent thread and prove it stopped.

    ``thread.join(timeout=2.0)`` returns whether or not the thread stopped, and
    every test here then indexed a dict the thread was supposed to fill - so a
    hung agent thread surfaced as ``KeyError: 'decision'``, a sentence about a
    dictionary rather than about the thread that never wrote to it.
    """
    budget = JOIN_BUDGET_S if budget_s is None else budget_s
    source = "the module default" if budget_s is None else "fixed by the caller, not the default"
    begun = time.monotonic()
    thread.join(timeout=budget)
    if thread.is_alive():
        raise AssertionError(
            f"the agent thread for {what} was still running {time.monotonic() - begun:.2f}s "
            f"after a {budget:.2f}s join ({source}); the live thread is {thread.name}, and "
            f"nothing it writes later will be read by this test"
        )


def _frame(frames: list[dict], kind: str) -> dict | None:
    return next((frame for frame in frames if frame.get("kind") == kind), None)



def test_approval_allow_returns_decision(tmp_path: Path) -> None:
    service = _service(tmp_path)
    frames: list[dict] = []
    result: dict = {}
    thread = threading.Thread(target=lambda: result.update(service.request_approval(
        session_id="s1", task_id="t1", tool="bash",
        arguments={"command": "make"}, risk="exec", reason="需要执行命令",
        on_event=frames.append, timeout=5.0,
    )))
    thread.start()
    request = _wait_for(
        "the approval_request frame", lambda: _frame(frames, "approval_request")
    )
    assert request["tool"] == "bash"
    assert request["preview"] == "make"
    resolved = service.resolve_approval(request["request_id"], "allow")
    _joined("a bash approval the user allowed", thread)
    assert resolved["resolved"] is True
    assert result["decision"] == "allow"
    assert result["timed_out"] is False
    assert any(f["kind"] == "approval_resolved" and f["decision"] == "allow" for f in frames)


def test_approval_always_marks_decision(tmp_path: Path) -> None:
    service = _service(tmp_path)
    frames: list[dict] = []
    result: dict = {}
    thread = threading.Thread(target=lambda: result.update(service.request_approval(
        session_id="s1", task_id="t1", tool="write_file",
        arguments={"path": "a.py"}, risk="write", reason="需要写入",
        on_event=frames.append, timeout=5.0,
    )))
    thread.start()
    request = _wait_for(
        "the approval_request frame", lambda: _frame(frames, "approval_request")
    )
    service.resolve_approval(request["request_id"], "always")
    _joined("a write_file approval the user chose to always allow", thread)
    assert result["decision"] == "always"


def test_approval_timeout_auto_denies(tmp_path: Path) -> None:
    service = _service(tmp_path)
    frames: list[dict] = []
    started = time.monotonic()
    verdict = service.request_approval(
        session_id="s1", task_id="t1", tool="write_file",
        arguments={"path": "a.py"}, risk="write", reason="需要写入",
        on_event=frames.append, timeout=0.3,
    )
    assert verdict["decision"] == "deny"
    assert verdict["timed_out"] is True
    assert 0.2 <= time.monotonic() - started < 3.0
    resolved = next(f for f in frames if f["kind"] == "approval_resolved")
    assert resolved["decision"] == "deny" and resolved["timed_out"] is True


def test_approval_cancel_exits_fast(tmp_path: Path) -> None:
    service = _service(tmp_path)
    cancel = threading.Event()
    frames: list[dict] = []
    box: dict = {}
    thread = threading.Thread(target=lambda: box.update(service.request_approval(
        session_id="s1", task_id="t1", tool="bash",
        arguments={"command": "sleep 5"}, risk="exec", reason="x",
        on_event=frames.append, cancel_event=cancel, timeout=30.0,
    )))
    thread.start()
    # The 0.1s beat stood in for "the prompt is on screen and the thread is parked
    # on it"; cancel before that and this test measures cancelling an idle
    # request.  The prompt frame is the same fact, written by the thread itself,
    # so wait for it instead of assuming it (M8-T70).
    frame = _wait_for(
        "the approval request frame that parks the thread",
        lambda: _frame(frames, "approval_request"),
    )
    assert frame["name"] == "bash" and frame["status"] == "pending"
    cancel.set()
    _joined("a bash approval cancelled by the task", thread)
    assert box["decision"] == "deny"
    assert box["cancelled"] is True


def test_similar_inflight_calls_merge_into_one_prompt(tmp_path: Path) -> None:
    service = _service(tmp_path)
    frames: list[dict] = []
    results: list[dict] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            verdict = service.request_approval(
                session_id="s1", task_id="t1", tool="bash",
                arguments={"command": "make all"}, risk="exec", reason="x",
                on_event=lambda e: frames.append(e), timeout=5.0,
            )
        except BaseException as exc:  # noqa: BLE001 - collected so the gate can name it
            # Same shape as test_concurrent_thread_saves_never_corrupt above: without this,
            # a worker that raises leaves results short and the only message is
            # "assert 1 == 2", which is about a list, not about the merge that failed.
            with lock:
                errors.append(exc)
            return
        with lock:
            results.append(verdict)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()

    def merged_waiters() -> int:
        """How many callers are parked on the single pending group, or 0.

        0 while there is not exactly one group, so "two waiters" cannot be
        satisfied by two unmerged groups of one waiter each - which is the other
        thing a fixed beat used to be unable to tell apart.
        """
        with service._approval_guard:
            groups = list(service._approval_groups.values())
        if len(groups) != 1:
            return 0
        return len(groups[0].waiters)

    # Both threads park on the identical merge_key → exactly one pending group.
    # The beat used to be ``sleep(0.1)`` followed by ``len(group.waiters) >= 1``.
    # Measured against planted mechanisms in a scratch worktree (three lags for
    # the second caller: 0.0s, 0.3s, 1.2s; the beat checks at ~0.11s):
    #   merge lookup disabled      -> old red, new red   (2 prompts shown)
    #   merged caller never attaches to the group -> old GREEN, new red (1 prompt)
    #   nothing planted            -> old green, new green
    # So the old shape's ``len(groups) == 1`` was watching the merge itself; the
    # part the beat could not see was whether the second caller is *in* the group
    # it merged into - which is the difference between one prompt waking two
    # callers and one prompt waking none of the parked ones.  The waiter count is
    # that fact, it is readable here, so wait for it and assert the number this
    # test's own name claims (M8-T70).
    # budget_s is widened from the module default because this predicate waits on
    # two thread starts reaching the service, not on one frame being appended.
    _wait_for(
        "both identical calls parked on one approval group",
        lambda: merged_waiters() == 2,
        budget_s=MERGE_BUDGET_S,
    )
    with service._approval_guard:
        assert len(service._approval_groups) == 1, "identical calls must merge"
        request_id = next(iter(service._approval_groups))
        group = service._approval_groups[request_id]
        assert len(group.waiters) == 2, "both identical calls must be parked on the group"
    service.resolve_approval(request_id, "allow")
    for index, t in enumerate(threads):
        _joined(f"merged waiter #{index}", t, budget_s=3.0)
    assert not errors, f"a merged waiter raised: {errors!r}"
    assert len(results) == 2, results
    assert all(r["decision"] == "allow" for r in results)
    # Only one prompt was shown to the user for two identical calls.
    assert len([f for f in frames if f["kind"] == "approval_request"]) == 1


def test_resolve_unknown_is_noop(tmp_path: Path) -> None:
    service = _service(tmp_path)
    assert service.resolve_approval("missing", "allow")["resolved"] is False


def test_resolve_rejects_bad_decision(tmp_path: Path) -> None:
    service = _service(tmp_path)
    with pytest.raises(ValueError):
        service.resolve_approval("nope", "maybe")


def test_deny_all_approvals_unblocks_waiters(tmp_path: Path) -> None:
    service = _service(tmp_path)
    frames: list[dict] = []
    box: dict = {}
    thread = threading.Thread(target=lambda: box.update(service.request_approval(
        session_id="s1", task_id="t1", tool="bash",
        arguments={"command": "make"}, risk="exec", reason="x",
        on_event=frames.append, timeout=30.0,
    )))
    thread.start()
    _wait_for("the approval_request frame", lambda: _frame(frames, "approval_request"))
    service._deny_all_approvals()
    _joined("a bash approval denied by the blanket sweep", thread)
    assert box["decision"] == "deny"
    assert service._approval_groups == {}


def test_preview_redacts_secrets(tmp_path: Path) -> None:
    service = _service(tmp_path)
    preview = service._approval_preview(
        "bash", {"command": "export MINICC_API_KEY=sk-abcdefgh12345678 && make"}
    )
    assert "sk-abcdefgh12345678" not in preview
    assert "REDACTED" in preview


# ---------------------------------------------------------------------------
# M8-T62: the waits themselves
# ---------------------------------------------------------------------------


def test_a_wait_that_misses_names_the_wait_not_the_assert(tmp_path: Path) -> None:
    """A missed in-process wait has to be readable, and it has to say where its
    own budget came from.

    The four call sites this file used to have could only print the value of the
    expression they asserted on - ``assert []`` where the predicate built a list,
    ``assert False is True`` where it returned a bool.  Forcing the miss with a
    budget tighter than the machine is the only way to read the failure branch, so
    this waits on a frame list that nothing ever appends to.
    """
    service = _service(tmp_path)
    frames: list[dict] = []
    assert service is not None, "the service exists only to prove nothing published"
    try:
        _wait_for(
            "a frame nothing will ever append",
            lambda: _frame(frames, "approval_request"),
            budget_s=0.25,
        )
    except AssertionError as failure:
        message = str(failure)
    else:
        raise AssertionError("the tight budget did not fire: the wait is not bounded")
    assert "gave up after " in message, message
    assert "waiting for a frame nothing will ever append" in message, message
    assert "0.25s budget" in message, message
    assert "fixed by the caller, not the default" in message, message
    assert "the module default" not in message, (
        f"a caller-supplied budget may not borrow the default's provenance: {message}"
    )
    # polls > 1 is the proof the loop actually polled rather than failing on sight
    polls = int(message.split("polls=")[1].split(")")[0])
    assert polls >= 2, message
    elapsed = float(message.split("gave up after ")[1].split("s ")[0])
    assert 0.25 <= elapsed < 2.0, f"elapsed {elapsed} does not respect the 0.25s budget"


def test_the_default_budget_is_the_one_named_when_no_caller_supplies_it(tmp_path: Path) -> None:
    """The other provenance branch, on the budget the four sites actually use.

    Costs a whole default budget of wall time on purpose: the number named in the
    message has to be the number the loop bounded itself by, and only a real miss
    can show that.
    """
    begun = time.monotonic()
    try:
        _wait_for("a frame that never arrives", lambda: False)
    except AssertionError as failure:
        message = str(failure)
    else:
        raise AssertionError("the default budget did not fire")
    spent = time.monotonic() - begun
    assert f"of a {PUBLISH_BUDGET_S:.2f}s budget" in message, message
    assert "the module default" in message, message
    assert "fixed by the caller" not in message, message
    assert spent >= PUBLISH_BUDGET_S, f"the message claims {PUBLISH_BUDGET_S}s, the wait lasted {spent:.2f}s"


def test_a_wait_returns_the_value_the_predicate_saw(tmp_path: Path) -> None:
    """``-> bool`` could not carry a request_id, and the tests need one.

    The old helper returned ``True`` from inside the loop and the raw predicate
    value only after the deadline, so a caller had to re-scan ``frames`` for the
    frame it had just been told about - and that re-scan is a second look at a
    list another thread is still appending to.
    """
    service = _service(tmp_path)
    frames: list[dict] = []
    thread = threading.Thread(target=lambda: service.request_approval(
        session_id="s1", task_id="t1", tool="bash",
        arguments={"command": "make"}, risk="exec", reason="x",
        on_event=frames.append, timeout=30.0,
    ))
    thread.start()
    request: dict = {}
    try:
        request = _wait_for(
            "the approval_request frame", lambda: _frame(frames, "approval_request")
        )
        assert isinstance(request, dict), f"a bool cannot carry the frame: {request!r}"
        assert request["kind"] == "approval_request"
        assert "request_id" in request
        # the returned frame is the one still in the list, not a stale copy
        assert _frame(frames, "approval_request") is request
    finally:
        if request:
            service.resolve_approval(request["request_id"], "deny")
        else:
            service._deny_all_approvals()
        _joined("the released approval thread", thread, budget_s=5.0)


def test_the_two_budgets_are_what_the_measurement_concludes(tmp_path: Path) -> None:
    """The budgets have to be defended by a number, not by habit.

    On HEAD, replacing the 2.0s default with 0.0 left every gate green, so nothing
    in this file was decided *by* the budget - which is how a patience constant
    stops being a decision.  This is the non-temporal half of the same judgement:
    the constants must stay above the measured envelope with room to spare.
    LOADED_ENVELOPE_S is the worst of the three in-process latencies recorded in
    this file's docstring on a loaded machine (969ms publish, 1015ms group check,
    719ms cancel), rounded up.
    """
    loaded_envelope_s = 1.0
    assert PUBLISH_BUDGET_S > 0.0 and JOIN_BUDGET_S > 0.0
    assert PUBLISH_BUDGET_S >= 2 * loaded_envelope_s, (
        f"the publish budget is {PUBLISH_BUDGET_S}s but a loaded machine needed "
        f"{loaded_envelope_s}s just to get the frame out"
    )
    assert JOIN_BUDGET_S >= 2 * loaded_envelope_s, (
        f"the join budget is {JOIN_BUDGET_S}s but a cancel took {loaded_envelope_s}s"
        " to surface on a loaded machine"
    )


def test_a_thread_that_never_returns_is_reported_as_a_thread(tmp_path: Path) -> None:
    """Where a hung agent thread used to surface as ``KeyError: 'decision'``.

    ``join(timeout=2.0)`` returns even when the thread is alive, and the next line
    indexed the dict that thread was supposed to fill.  This leaves the approval
    unresolved on purpose, so the box really is still empty at the moment of the
    failure - that emptiness is the whole reason the old message named a
    dictionary instead of the thread.
    """
    service = _service(tmp_path)
    frames: list[dict] = []
    box: dict = {}
    thread = threading.Thread(target=lambda: box.update(service.request_approval(
        session_id="s1", task_id="t1", tool="bash",
        arguments={"command": "make"}, risk="exec", reason="x",
        on_event=frames.append, timeout=30.0,
    )))
    thread.start()
    request: dict = {}
    try:
        request = _wait_for(
            "the approval_request frame", lambda: _frame(frames, "approval_request")
        )
        assert box == {}, "an empty box is what used to raise KeyError: 'decision'"
        with pytest.raises(AssertionError) as caught:
            _joined("an approval nobody resolves", thread, budget_s=0.2)
        message = str(caught.value)
        assert "was still running" in message, message
        assert "an approval nobody resolves" in message, message
        assert "0.20s join" in message, message
        assert "fixed by the caller, not the default" in message, message
        assert "KeyError" not in message, message
    finally:
        if request:
            service.resolve_approval(request["request_id"], "deny")
        else:
            service._deny_all_approvals()
        _joined("the approval released by the finally", thread, budget_s=5.0)
    assert box["decision"] == "deny"
    assert box["timed_out"] is False


# ---------------------------------------------------------------------------
# M7-T3 acceptance, end to end: the should_allow chain inside _chat_locked.
# The gates above exercise request_approval/resolve_approval directly; this one
# walks the real web entry so a regression that breaks the wiring — rules not
# consulted, the gate never asking, "always" not remembered — turns red here.
# ---------------------------------------------------------------------------


def test_web_default_mode_asks_then_always_is_undisturbed(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace

    from minicc import web as web_module
    from minicc.llm.base import LLMResponse

    class _WriteThenAnswer:
        instances: list["_WriteThenAnswer"] = []

        def __init__(self, *args, **kwargs) -> None:
            from minicc.llm.fake import FakeProvider

            # The judge round (tools is None) is delegated to the scripted
            # FakeProvider: its decision JSON is the contract the web loop
            # parses, and a hand-written script cannot honor it.
            self._inner = FakeProvider()
            self.calls = 0
            _WriteThenAnswer.instances.append(self)

        async def chat(self, messages, tools, on_delta=None):
            if tools is None:
                return await self._inner.chat(messages, None, on_delta)
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(
                    content="",
                    tool_calls=[{
                        "id": f"call-{len(_WriteThenAnswer.instances)}",
                        "type": "function",
                        "function": {
                            "name": "write_file",
                            "arguments": json.dumps({"path": "b.txt", "content": "approved\n"}),
                        },
                    }],
                    finish_reason="tool_calls",
                )
            if self.calls == 2:
                # The completion judge refuses to certify an unexamined write:
                # the run must observe the file after writing it (a read back
                # suffices for prose). Without this round the judge demotes
                # "complete" to "continue" until the cap fires.
                return LLMResponse(
                    content="",
                    tool_calls=[{
                        "id": f"call-read-{len(_WriteThenAnswer.instances)}",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": json.dumps({"path": "b.txt"}),
                        },
                    }],
                    finish_reason="tool_calls",
                )
            return LLMResponse(content="完成。", finish_reason="stop")

        async def close(self) -> None:
            return await self._inner.close()

    _WriteThenAnswer.instances = []
    monkeypatch.setattr(web_module, "OpenAICompatibleProvider", _WriteThenAnswer)
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
        # The turn counter is broader than "agent chat calls" (review and
        # recovery rounds count too); this gate pins the approval wiring, not
        # the budget arithmetic, so leave headroom for the whole happy path.
        max_turns=12,
        compact_threshold=300_000,
        context_window_tokens=300_000,
        fallback_models=(),
    )
    service = web_module.AgentService(tmp_path, config)
    box: dict = {}
    frames: list[dict] = []

    def _run_task() -> None:
        box["result"] = service._chat_locked(
            {
                "message": "写一个 b.txt",
                "session_id": "approval-e2e",
                "allow_changes": False,
                "workspace_path": str(tmp_path),
            },
            workspace=tmp_path,
            on_event=frames.append,
        )

    thread = threading.Thread(target=_run_task)
    thread.start()

    def pending_request_id() -> str | None:
        with service._approval_guard:
            groups = [g for g in service._approval_groups.values() if not g.resolved]
        return groups[0].request_id if groups else None

    try:
        # The full agent has to boot before the write reaches the gate, so the
        # budget here covers a service start, not one frame append.
        request_id = _wait_for("the pending write_file approval", pending_request_id,
                               budget_s=30.0)
        service.resolve_approval(request_id, "always")
        _joined("the parked agent thread after 'always'", thread, budget_s=30.0)
    except BaseException:
        service._deny_all_approvals()
        _joined("the agent thread released by the failure sweep", thread, budget_s=60.0)
        raise

    result = box["result"]
    assert result["error"] is None, result.get("error")
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "approved\n", (
        "the approved write never executed"
    )
    # The ask/answer travel the SSE frame channel (what the front end renders),
    # the *decision* lands in the task's own event list (what audit reads).
    asked = [f for f in frames if f.get("code") == "approval_requested"]
    assert len(asked) == 1, f"expected exactly one prompt for one write: {len(asked)}"
    assert asked[0]["tool"] == "write_file" and "b.txt" in asked[0]["preview"]
    resolved_frames = [f for f in frames if f.get("code") == "approval_resolved"]
    assert resolved_frames and resolved_frames[0]["decision"] == "always", resolved_frames
    authorized = [e for e in result["events"] if e.get("code") == "tool_authorized"]
    assert any(e.get("authorization") == "user_approved" for e in authorized), (
        "the allow branch never wrote its audit event"
    )

    # "always" taught the session: the identical write runs again without a
    # second prompt (zero-disturbance, scoped to one session and one path —
    # the remembered rule can never widen plan/yolo semantics).
    _WriteThenAnswer.instances = []
    frames.clear()
    second = service._chat_locked(
        {
            "message": "再写一次 b.txt",
            "session_id": "approval-e2e",
            "allow_changes": False,
            "workspace_path": str(tmp_path),
        },
        workspace=tmp_path,
        on_event=frames.append,
    )
    assert second["error"] is None, second.get("error")
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "approved\n"
    assert "approval_requested" not in [f.get("code") for f in frames], (
        "the remembered session rule did not spare the user a second prompt"
    )
    second_authorized = [e for e in second["events"] if e.get("code") == "tool_authorized"]
    assert any(
        e.get("authorization") == "session_allowlist" for e in second_authorized
    ), f"the rerun was authorized by something other than the session rule: {second_authorized}"
    service.shutdown()

