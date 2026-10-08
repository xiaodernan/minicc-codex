"""Permission mode tests: normalize, authorize_tool modes, task submit wiring."""

from __future__ import annotations

import threading
import types
from pathlib import Path

import pytest

from minicc.audit import authorize_tool, normalize_permission_mode
from minicc.web import AgentService, _resolve_task_permissions
from minicc.webauth import WebAuth


# ---------------------------------------------------------------------------
# normalize_permission_mode
# ---------------------------------------------------------------------------


def test_normalize_permission_mode_aliases_and_errors() -> None:
    assert normalize_permission_mode(None) == "default"
    assert normalize_permission_mode("") == "default"
    assert normalize_permission_mode("normal") == "default"
    assert normalize_permission_mode("PLAN") == "plan"
    assert normalize_permission_mode("acceptEdits") == "acceptEdits"
    assert normalize_permission_mode("yolo") == "yolo"
    with pytest.raises(ValueError, match="permission_mode"):
        normalize_permission_mode("danger")


# ---------------------------------------------------------------------------
# authorize_tool mode semantics
# ---------------------------------------------------------------------------


def test_plan_mode_denies_write_and_exec_but_allows_readonly() -> None:
    write = authorize_tool(
        "write_file", "write", {}, allow_changes=True, allow_network=True, permission_mode="plan"
    )
    assert write.allowed is False
    assert write.authorization == "plan_mode_write"
    run = authorize_tool(
        "bash", "exec", {"command": "python -m pytest -q"}, allow_changes=True, allow_network=True, permission_mode="plan"
    )
    assert run.allowed is False
    read = authorize_tool(
        "read_file", "readonly", {}, allow_changes=False, allow_network=False, permission_mode="plan"
    )
    assert read.allowed is True


def test_plan_mode_still_allows_authorized_network_research() -> None:
    search = authorize_tool(
        "web_search", "readonly", {}, allow_changes=False, allow_network=True, permission_mode="plan"
    )
    assert search.allowed is True
    denied = authorize_tool(
        "web_search", "readonly", {}, allow_changes=False, allow_network=False, permission_mode="plan"
    )
    assert denied.allowed is False


def test_accept_edits_auto_allows_writes_but_not_exec() -> None:
    write = authorize_tool(
        "write_file", "write", {}, allow_changes=False, allow_network=False, permission_mode="acceptEdits"
    )
    assert write.allowed is True
    # Non-whitelisted exec still requires explicit write authorization, even
    # in acceptEdits; the read-only pytest whitelist stays available because
    # it is verification, not mutation.
    run = authorize_tool(
        "bash", "exec", {"command": "node scripts/build.js"}, allow_changes=False, allow_network=False, permission_mode="acceptEdits"
    )
    assert run.allowed is False
    safe_run = authorize_tool(
        "bash", "exec", {"command": "python -m pytest -q"}, allow_changes=False, allow_network=False, permission_mode="acceptEdits"
    )
    assert safe_run.allowed is True
    other_exec = authorize_tool(
        "bash", "exec", {"command": "node scripts/build.js"}, allow_changes=True, allow_network=False, permission_mode="acceptEdits"
    )
    assert other_exec.allowed is True


def test_yolo_mode_allows_everything() -> None:
    for tool, risk, args in (
        ("write_file", "write", {}),
        ("bash", "exec", {"command": "curl https://example.test"}),
        ("web_search", "readonly", {"query": "x"}),
    ):
        decision = authorize_tool(tool, risk, args, allow_changes=False, allow_network=False, permission_mode="yolo")
        assert decision.allowed is True
        assert decision.authorization == "task_yolo"


def test_default_mode_backward_compatible() -> None:
    assert authorize_tool("write_file", "write", {}, allow_changes=False, allow_network=False).allowed is False
    assert authorize_tool("write_file", "write", {}, allow_changes=True, allow_network=False).allowed is True
    assert authorize_tool("bash", "exec", {"command": "python -m pytest -q"}, allow_changes=False, allow_network=False).allowed is True


# ---------------------------------------------------------------------------
# task submit wiring
# ---------------------------------------------------------------------------


def _service(tmp_path: Path) -> AgentService:
    config = types.SimpleNamespace(
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
    )
    return AgentService(tmp_path, config)


def _own_model_turns(seen_requests: list[list[dict]], prompt: str) -> list[list[dict]]:
    """This run's own model turns, out of every call the patch window caught.

    The provider patch is module-level, so while it is installed *any*
    service in the process that builds a provider records into the same
    list - a leftover background run from an earlier test included
    (batch 201's 1-in-24 flake). Selecting by the run's own user message
    is what separates our turns from a foreign call that merely shares
    the window.
    """
    own: list[list[dict]] = []
    for messages in seen_requests:
        if any(
            message.get("role") == "user"
            and str(message.get("content") or "").strip() == prompt
            for message in messages
        ):
            own.append(messages)
    return own


def test_resolve_task_permissions_modes(tmp_path: Path) -> None:
    changes, network, mode = _resolve_task_permissions({"allow_changes": True}, yolo=False)
    assert (changes, network, mode) == (True, False, "default")

    changes, network, mode = _resolve_task_permissions({"permission_mode": "yolo"}, yolo=False)
    assert (changes, network, mode) == (True, True, "yolo")

    changes, network, mode = _resolve_task_permissions(
        {"permission_mode": "plan", "allow_changes": True}, yolo=False
    )
    # Both transports carry effective permissions. A conflicting raw flag
    # must not survive plan normalization into a later execution adapter.
    assert (changes, network, mode) == (False, False, "plan")

    with pytest.raises(ValueError, match="permission_mode"):
        _resolve_task_permissions({"permission_mode": "chaos"}, yolo=False)


def test_snapshot_round_trip_preserves_permission_mode(tmp_path: Path) -> None:
    service = _service(tmp_path)
    try:
        # _defer_schedule: the record is what this test reads, and a
        # scheduled run would hit the unreachable example.test endpoint
        # from a background thread - the exact intruder batch 201's flake
        # chased. Every other suite test that only wants a record defers.
        submitted = service.tasks.submit(
            {
                "message": "只做规划",
                "permission_mode": "plan",
                "allow_changes": True,
                "_defer_schedule": True,
            }
        )
        task_id = submitted["task_id"]
        snapshot = service.tasks.get(task_id)
        assert snapshot["permission_mode"] == "plan"
        assert snapshot["allow_changes"] is False

        submitted_yolo = service.tasks.submit(
            {"message": "全自动", "permission_mode": "yolo", "_defer_schedule": True}
        )
        yolo_snapshot = service.tasks.get(submitted_yolo["task_id"])
        assert yolo_snapshot["permission_mode"] == "yolo"
        assert yolo_snapshot["allow_changes"] is True
        assert yolo_snapshot["allow_network"] is True
    finally:
        service.shutdown()


def test_submit_rejects_invalid_permission_mode(tmp_path: Path) -> None:
    service = _service(tmp_path)
    try:
        with pytest.raises(ValueError, match="permission_mode"):
            service.tasks.submit({"message": "x", "permission_mode": "chaos"})
    finally:
        service.shutdown()


def test_plan_mode_injects_system_notice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Plan mode tells the model up front that writes are unavailable."""
    import copy

    from minicc.llm.base import LLMResponse
    from minicc.web import AgentService as _AS

    seen_requests: list[list[dict]] = []

    class FakeProvider:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def chat(self, messages, tools, on_delta=None):
            seen_requests.append(copy.deepcopy(messages))
            return LLMResponse(content="计划模式调研结论。")

        async def close(self):
            return None

    monkeypatch.setattr("minicc.web.OpenAICompatibleProvider", FakeProvider)
    prompt = "调研并输出计划"
    service = _service(tmp_path)
    try:
        run_result = service._chat_locked(
            {"message": prompt, "permission_mode": "plan", "workspace_path": str(tmp_path)},
            workspace=tmp_path,
        )
    finally:
        service.shutdown()
    # Failure shape matters: this test flaked once in 24 combination runs
    # (2026-10-08, observed, never reproduced again; batch 201 hunted it for
    # 30 further trials with the same five files and never saw it again).
    # Batch 201 then reproduced the shape deterministically and found the
    # mechanism: the provider patch is module-level, so a background run
    # left over from an earlier test in the same session records its own
    # request into this capture list, and on a contended machine that
    # foreign [system, user] call is exactly what the red reported. The
    # capture is therefore scoped to this run's own model turns - see
    # test_plan_mode_notice_survives_a_foreign_call_in_the_same_process
    # below, which builds the foreign call on purpose. The empty shape
    # (no provider call at all) still reports itself, with the run's own
    # error, so a future occurrence says whether the run died before or
    # after the call.
    assert seen_requests, (
        "plan mode must issue at least one provider request; "
        f"requests=0 run_error={getattr(run_result, 'error', None)!r} "
        f"run_answer={getattr(run_result, 'answer', None)!r}"
    )
    own_turns = _own_model_turns(seen_requests, prompt)
    assert own_turns, (
        "plan mode must issue at least one provider request of its own; "
        f"requests={len(seen_requests)} carried no message of this run, "
        f"run_error={getattr(run_result, 'error', None)!r}"
    )
    first_request = own_turns[0]
    notice = [
        message for message in first_request if "计划模式" in str(message.get("content") or "")
    ]
    assert notice, (
        "plan mode must inject its system notice into the first provider request; "
        f"saw roles={[str(m.get('role')) for m in first_request]}, "
        f"requests={len(seen_requests)} (own turns: {len(own_turns)}), "
        f"run_error={getattr(run_result, 'error', None)!r}"
    )


def test_plan_mode_notice_survives_a_foreign_call_in_the_same_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Batch 201: the batch-199 flake's shape, rebuilt deterministically.

    What the 1-in-24 red actually was: the capture list is process-global
    through the module-level provider patch, and a background run left
    over from an earlier test in the same session was starved by a
    contended machine (201s against a usual 40s) long enough to build its
    provider *inside* this test's patch window. Its [system, user] request
    landed in the same list, ahead of ours, and a bare "first request has
    the notice" read that as a missing notice.

    This test rebuilds the shape on purpose - a foreign service's run
    records first - and asserts the scoped check still finds the notice
    in this run's own model turn. The naive shape is asserted too, so the
    reproduction stays honest: if a future change makes the foreign call
    invisible, this test says so instead of silently passing.
    """
    import copy

    from minicc.llm.base import LLMResponse

    prompt = "调研并输出计划"
    foreign_prompt = "外来后台任务的消息"
    seen_requests: list[list[dict]] = []
    foreign_recorded = threading.Event()

    class FakeProvider:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def chat(self, messages, tools, on_delta=None):
            seen_requests.append(copy.deepcopy(messages))
            if any(
                message.get("role") == "user"
                and str(message.get("content") or "").strip() == foreign_prompt
                for message in messages
            ):
                foreign_recorded.set()
            return LLMResponse(content="外来结论。")

        async def close(self):
            return None

    monkeypatch.setattr("minicc.web.OpenAICompatibleProvider", FakeProvider)
    foreign_dir = tmp_path / "foreign"
    foreign_dir.mkdir()
    foreign = _service(foreign_dir)
    foreign_error: list[BaseException] = []

    def run_foreign() -> None:
        try:
            foreign._chat_locked(
                {"message": foreign_prompt, "workspace_path": str(foreign_dir)},
                workspace=foreign_dir,
            )
        except BaseException as exc:  # noqa: BLE001 - reported below
            foreign_error.append(exc)

    foreign_thread = threading.Thread(
        target=run_foreign, daemon=True, name="t201-foreign-run"
    )
    foreign_thread.start()
    assert foreign_recorded.wait(timeout=60), (
        "the reproduction needs the foreign run's provider call to be "
        "recorded before ours; without it this test proves nothing"
    )
    service = _service(tmp_path)
    try:
        service._chat_locked(
            {"message": prompt, "permission_mode": "plan", "workspace_path": str(tmp_path)},
            workspace=tmp_path,
        )
    finally:
        service.shutdown()
        foreign.shutdown()
        foreign_thread.join(timeout=60)
    assert not foreign_thread.is_alive(), "the foreign run never finished"
    assert not foreign_error, f"the foreign run raised: {foreign_error!r}"
    # The reproduction is faithful only if the naive reading would have
    # failed: the first recorded request is the foreign one, without our
    # notice.
    assert not any(
        "计划模式" in str(message.get("content") or "") for message in seen_requests[0]
    ), "the foreign call must not carry our notice - otherwise this is not the flake's shape"
    own_turns = _own_model_turns(seen_requests, prompt)
    assert own_turns, (
        "this run must have issued at least one provider request of its "
        f"own; requests={len(seen_requests)}"
    )
    first_request = own_turns[0]
    notice = [
        message for message in first_request if "计划模式" in str(message.get("content") or "")
    ]
    assert notice, (
        "plan mode must inject its system notice into the first provider "
        f"request even when a foreign call shares the capture list; "
        f"saw roles={[str(m.get('role')) for m in first_request]}, "
        f"requests={len(seen_requests)} (own turns: {len(own_turns)})"
    )
